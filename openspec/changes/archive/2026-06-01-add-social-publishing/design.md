## Context

### 既存アプリの状態
- バックエンド: FastAPI / Python 3.11、**DB なし**（`/api/process` 等のステートレスな動画処理 API）
- フロント: Next.js 16、単一ページの編集ウィザード（`frontend/app/page.tsx`）。ルーティング/サブページは未整備
- 既存投稿系コード:
  - `services/instagram.py`: Graph API v21 で Reels 投稿フルフロー実装済み（container 作成 → status ポーリング → publish）。ただし**認証は env 変数**（`INSTAGRAM_ACCESS_TOKEN` / `INSTAGRAM_BUSINESS_ACCOUNT_ID`）
  - `services/tiktok.py` / `routers/publish.py`: job_id ベースの即時投稿。Google Sheets からキャプション取得。今回の予約投稿モデルとは別物（流用しない）
  - **YouTube 連携は未実装**
- Docker Compose: backend(8001) / frontend(3002)。volume は `backend-tmp` / `hf-cache`

### 確定した運用前提（ユーザー回答）
- 実行環境: **ローカル Docker のみ**
- SNS アカウント: **別途 OAuth 連携したい**（env ベタ書きではない）
- 進め方: OpenSpec change 起票から

## Goals / Non-Goals

**Goals:**
- TikTok で保存した字幕付き MP4 をアップロード → IG Reels / YT Shorts に予約投稿
- IG / YT で別々の予約日時を指定可能
- 投稿ステータス管理・履歴・エラー表示・手動リトライ・今すぐ投稿
- 二重投稿の防止
- 既存編集パイプラインを壊さない（投稿は独立 capability）

**Non-Goals:**
- TikTok 自動投稿 / Edits API / 自動字幕生成 / 無音削除（編集側のスコープ）
- 複数アカウント管理・チーム権限
- 高度な分析・コメント/DM 管理
- AI キャプション生成（要件定義書 §12、将来別 change）
- 本番デプロイ / スケール対応（ローカル Docker 前提）

## Decisions

### D1: DB は Postgres + SQLAlchemy + Alembic（Supabase 不採用）
実行環境がローカル Docker のみのため、Supabase / Vercel は採用せず Docker Compose 内に Postgres を立てる。要件定義書のデータモデル（uuid PK / timestamp）にそのまま準拠でき、二重投稿防止に必要な行ロック（`FOR UPDATE SKIP LOCKED`）と atomic claim（`UPDATE ... RETURNING`）が使える。

- SQLite も候補だが、cron と「今すぐ投稿」が同時実行されうるため、行ロックが堅い Postgres を選ぶ
- 接続: sync SQLAlchemy + `psycopg2-binary`（既存コードが sync requests ベースで統一しやすい）
- マイグレーション: Alembic

### D2: データモデル（要件定義書 §5 準拠）

```
videos
  id uuid PK / file_url / storage_path / original_filename / thumbnail_url
  duration_seconds / aspect_ratio / theme / memo / created_at / updated_at

scheduled_posts
  id uuid PK / video_id FK→videos
  platform (instagram|youtube) / scheduled_at / status
  caption / title / description / hashtags / privacy_status
  posted_url / external_post_id / error_message / retry_count / posted_at
  created_at / updated_at

social_connections
  id uuid PK / platform (instagram|youtube)
  account_name / external_account_id
  access_token / refresh_token / token_expires_at（暗号化保存）
  is_active / created_at / updated_at
```

- 動画 1 本に対し IG 用・YT 用の `scheduled_posts` を**別レコード**で持つ（別日時指定のため）
- status: `draft` / `scheduled` / `posting` / `posted` / `failed` / `cancelled`

### D3: 動画ストレージとメディア配信
- アップロード動画は Docker volume `media-storage`（`/app/media/{video_id}/source.mp4`）に保存
- `storage_path` = コンテナ内パス、`file_url` = `{PUBLIC_BASE_URL}/api/posts/media/{video_id}`
- 配信は既存 `serve_media` パターンの FileResponse を踏襲（`routers/posts.py`）
- サムネイル: ffmpeg で 1 フレーム抽出（既存 `services/ffmpeg.py` 活用）

### D4: Instagram 公開 URL とローカル Docker
Instagram Graph API は `video_url` に**外部からアクセス可能な HTTPS URL** を要求する（短命の署名 URL は不可）。ローカル Docker のみの運用では:

- 投稿時に **ngrok 等のトンネル**でバックエンドを公開し、`PUBLIC_BASE_URL` をトンネル URL に設定する
- IG は `{PUBLIC_BASE_URL}/api/posts/media/{video_id}` を取得する
- この前提を README / .env.example に明記する（IG 投稿を試すにはトンネル必須）

### D5: SNS 連携は OAuth + 暗号化トークン保存
ユーザー要望により env ベタ書きでなく OAuth 連携にする。

- **YouTube (Google OAuth 2.0)**: `routers/connections.py` で認可フロー → `refresh_token` を取得し `social_connections` に保存。投稿時に refresh して access_token を mint
- **Instagram (Meta OAuth)**: Facebook Login → 長期トークン + IG ビジネスアカウント ID を取得し保存。既存 `instagram.py` を connection ベースに改修（env フォールバックは残す）
- トークンは `services/crypto.py`（Fernet, `TOKEN_ENCRYPTION_KEY`）で暗号化して `access_token` / `refresh_token` カラムに保存
- ローカル Docker での redirect URI: Google は loopback（`http://localhost:8001/...`）可。Meta は HTTPS 必須のため ngrok URL を redirect に登録（D4 のトンネルを流用）

### D6: 予約実行（cron）と二重投稿防止
- バックエンド内 **APScheduler** を 1 分間隔で起動し `publisher.run_due_posts()` を呼ぶ（外部 cron 不要）
- 手動/外部トリガー用に `POST /api/cron/run`（`CRON_SECRET` 必須）も用意
- 二重投稿防止 = **atomic claim**:
  ```sql
  UPDATE scheduled_posts SET status='posting', updated_at=now()
  WHERE id = :id AND status IN ('scheduled','failed')
  RETURNING id;
  ```
  rowcount=1 のときのみ投稿実行。cron バッチ取得は `SELECT ... WHERE status='scheduled' AND scheduled_at<=now() FOR UPDATE SKIP LOCKED` で同一行の二重取得を防ぐ
- 投稿成功 → `posted` + `posted_url` / `external_post_id` / `posted_at`。失敗 → `failed` + `error_message`

### D7: 今すぐ投稿 / リトライ
- 今すぐ投稿: 対象 `scheduled_post` を即時 claim → 投稿。`posted` は再投稿しない。`failed` はリトライ扱い
- リトライ: `retry_count += 1` → `posting` → 再投稿（D6 の claim を通す）

### D8: バリデーション（要件定義書 §10）
- 動画: MP4 のみ / ファイルサイズ上限 / 縦動画推奨
- IG: caption 必須・IG ON なら scheduled_at 必須・IG connection 未設定なら投稿不可
- YT: title / description 必須・YT ON なら scheduled_at 必須・YT connection 未設定なら投稿不可
- 共通: 両媒体 OFF は保存不可 / 過去日時は警告し「今すぐ投稿」確認 / `posted` 済みは編集不可（複製して編集）

### D9: ハッシュタグ（要件定義書 §9）
- 各媒体最大 5 個。スペース or 改行区切り入力可
- 保存時に正規化: 空白除去 / 先頭 `#` 補完 / 6 個以上はエラー

### D10: フロントエンド構成
- `/`（新）: 「編集する」/「投稿する」の導線。編集は `/edit` へリンク
- `/edit`: 既存ウィザード（現 `page.tsx` を移設、ロジック無変更）
- `/post`: 一覧（サムネ / テーマ / 予定日時 / IG・YT ステータス / URL / 操作ボタン）
- `/post/new`: 作成（アップロード → プレビュー → テーマ → IG 設定 → YT 設定 → 予約 → 保存/今すぐ投稿）
- `/post/[id]`: 詳細（プレビュー / 投稿内容 / 予約状況 / 履歴 / エラー / リトライ）

### D11: YouTube 投稿（要件定義書 §8）
- `services/youtube.py`: `google-api-python-client` + `google-auth-oauthlib`
- `videos.insert`（snippet.title / description / tags, status.privacyStatus）。MVP デフォルト `public`
- レジューム可能アップロード（`MediaFileUpload`）。成功後 `https://youtu.be/{id}` を保存

## Risks / Trade-offs

### R1: IG 公開 URL（ローカル Docker）
**Mitigation**: ngrok トンネル前提を文書化。Phase 1（UI+DB）は公開 URL 不要なので先に完成させ、IG 実投稿は Phase 3 で検証。

### R2: OAuth redirect URI のローカル制約（特に Meta は HTTPS 必須）
**Mitigation**: D4 のトンネル URL を redirect にも流用。Google は loopback 可。OAuth は Phase 2/3 に隔離し Phase 1 をブロックしない。

### R3: 二重投稿（cron と今すぐ投稿の競合）
**Mitigation**: D6 の atomic claim（`UPDATE ... WHERE status IN (...) RETURNING`）+ `FOR UPDATE SKIP LOCKED`。

### R4: トークン漏洩
**Mitigation**: Fernet で暗号化保存（`TOKEN_ENCRYPTION_KEY`）。`.env` は gitignored。

### R5: 既存編集機能への影響
**Mitigation**: 投稿は独立 capability。編集パイプラインのコードは無変更。唯一の接点はトップ画面のルート移設（`/` → `/edit`）で、これは proposal で BREAKING 明記済み。

### R6: APScheduler の多重起動（reload 時など）
**Mitigation**: スケジューラはアプリ lifespan で 1 インスタンスのみ起動。ジョブ実行は D6 の claim で冪等。

## Migration Plan

### Phase 1: 基盤 + UI + 予約保存（投稿実行なし）
DB 基盤 / docker-compose Postgres / モデル / トップ分割 / 一覧 / 作成 / アップロード / バリデーション / ステータス保存。この時点で「保存できる・一覧で見える」まで。公開 URL も OAuth も不要。

### Phase 2: YouTube 投稿
Google OAuth 連携 / `youtube.py` / videos.insert / 成功 URL・エラー保存。単発で「今すぐ投稿」して動作確認。

### Phase 3: Instagram 投稿
Meta OAuth 連携 / 既存 `instagram.py` を connection ベースへ / ngrok で公開 URL 検証 / 成功 URL・エラー保存。

### Phase 4: 予約実行 + リトライ + 二重投稿防止 + 履歴
APScheduler / `publisher` / atomic claim / リトライ / 投稿履歴表示。予約時刻到来で自動投稿を確認。

### Rollback
投稿系は独立モジュール + 独立 DB。frontend のルート移設だけ戻せば編集機能は完全復旧。Postgres コンテナと投稿テーブルは drop で除去可能。git revert で全戻し可。
