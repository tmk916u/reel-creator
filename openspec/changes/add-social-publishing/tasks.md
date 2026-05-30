## Phase 1: 基盤 + UI + 予約保存（投稿実行なし）

> **Phase 1 の設計逸脱（合意済み）**
> - Alembic は導入せず、起動時 `Base.metadata.create_all()`（`db.init_db()`）でテーブル作成。スキーマ安定後に Alembic 導入（Phase 2+）。
> - 連携必須バリデーション（IG/YT connection 未設定なら投稿不可）は OAuth 実装が無い Phase 1 では無効化。Phase 2/3 で OAuth と同時に有効化する。`requirements.txt` の `apscheduler`/`cryptography` も使用フェーズ（Phase 2/4）で追加。
> - Phase 1 では検証を Docker フル起動ではなく「posts 専用バックエンド(sqlite) + frontend dev」で実施（ML 依存のリビルド回避）。

### 1.1 DB / インフラ基盤
- [x] `docker-compose.yml` に `db`（Postgres）サービス + `media-storage` volume を追加
- [x] `requirements.txt` に `sqlalchemy` `psycopg2-binary` を追加（alembic/apscheduler/cryptography は使用フェーズで追加）
- [x] `app/db.py`（engine / SessionLocal / Base / get_db 依存 / init_db）
- [x] `app/models/db_models.py`（videos / scheduled_posts / social_connections）
- [x] ~~Alembic 初期化~~ → 起動時 `create_all`（逸脱、上記参照）
- [x] `.env.example` を投稿系 env（DATABASE_URL / MEDIA_DIR / PUBLIC_BASE_URL / META_* / GOOGLE_* / CRON_SECRET / TOKEN_ENCRYPTION_KEY）に更新

### 1.2 バックエンド（投稿 CRUD + アップロード）
- [x] `app/models/schemas.py` に投稿系 Pydantic（UploadVideoResponse / PostCreate / PostUpdate / PostOut / ScheduledPostOut）
- [x] `app/services/storage.py`（media volume へストリーム保存 + サムネ抽出 = ffmpeg 1 フレーム + duration probe）
- [x] `app/services/hashtags.py`（正規化: 空白除去 / `#` 補完 / 重複除去 / 6 個以上エラー）
- [x] `app/routers/posts.py`:
  - `POST /api/posts/upload`（MP4 アップロード → videos 作成）
  - `POST /api/posts`（video + IG/YT scheduled_posts 作成、バリデーション D8）
  - `GET /api/posts`（一覧）/ `GET /api/posts/{id}`（詳細）
  - `PATCH /api/posts/{id}` / `DELETE /api/posts/{id}`
  - `GET /api/posts/media/{video_id}` + `/thumbnail`（FileResponse 配信）
- [x] `app/main.py` にルーター登録 + DB lifespan（init_db）
- [x] テスト（`tests/test_posts.py` + `tests/test_hashtags.py`）: アップロード / 作成バリデーション / ハッシュタグ正規化 / 一覧・詳細 → 21 件 pass

### 1.3 フロントエンド（トップ分割 + 一覧 + 作成）
- [x] 既存 `app/page.tsx` を `app/edit/page.tsx` へ移設（編集ロジック無変更）
- [x] `app/page.tsx` を「編集する / 投稿する」導線のトップに差し替え
- [x] `app/post/page.tsx`（一覧: サムネ / テーマ / 予定日時 / IG・YT ステータス / 操作ボタン）
- [x] `app/post/new/page.tsx`（アップロード → プレビュー → テーマ → IG 設定 → YT 設定 → 予約 → 保存）
- [x] `app/post/[id]/page.tsx`（詳細: プレビュー / 投稿内容 / 予約状況 / 履歴 / エラー / 編集）
- [x] `lib/api.ts` に投稿系クライアント追加 + `lib/datetime.ts`（JST）+ `components/PostStatusBadge.tsx`
- [x] frontend type check（tsc）/ eslint pass

### 1.4 Phase 1 検証
- [x] posts 専用バックエンド(sqlite) + frontend dev で全サービス起動
- [x] MP4 アップロード → IG/YT 予約を保存 → 一覧・詳細で確認（ブラウザ、スクショ取得）
- [x] backend 新規テスト全 pass（21 件）。既存 ML 依存テストは Docker フル起動時に確認

## Phase 2: YouTube 投稿

> **Phase 2 の補足**
> - `apscheduler` はまだ追加せず（Phase 4）。`cryptography` / `google-api-python-client` / `google-auth-oauthlib` を追加。
> - `publisher.run_due_posts()` も先行実装済み（Phase 4 の cron から呼ぶ）。
> - リトライ（`POST /api/posts/{post_id}/retry`）も先行実装。
> - 実機 YouTube 投稿はユーザーの Google Cloud OAuth クライアント設定が必要（未実施）。

- [x] `app/services/crypto.py`（Fernet トークン暗号化、鍵なし時は平文+warning）
- [x] `app/routers/connections.py`: Google OAuth（start / callback → refresh_token を `social_connections` に暗号化保存）+ 一覧 + 解除
- [x] `app/services/youtube.py`: Flow で auth_url/token交換、refresh_token → Credentials、`videos.insert`（snippet / status.privacyStatus）、チャンネル名取得、成功 URL
- [x] `app/services/publisher.py`: 単一 scheduled_post を atomic claim → platform 投稿 → ステータス更新（+ run_due_posts）
- [x] `routers/posts.py` に `POST /api/posts/{post_id}/publish_now` + `POST /api/posts/{post_id}/retry`
- [x] フロント: 連携設定 UI（`/post/connections` + YouTube 接続/解除）+ 詳細画面の「今すぐ投稿 / リトライ」
- [x] テスト: OAuth コールバック保存 / youtube publish（mock）/ claim 冪等性 / 復号 → 13 件 pass（全 34 件）
- [x] ブラウザ検証: 連携画面 / 接続ボタン → 未設定エラー / 今すぐ投稿（未連携→失敗記録→リトライ表示）
- [ ] 実機: 1 本を YouTube に今すぐ投稿して URL 保存を確認（**要 Google Cloud OAuth 設定**、ユーザー対応待ち）

## Phase 3: Instagram 投稿

> **Phase 3 の補足**
> - 既存 `publish_to_instagram(env版)` と `_create_container`/`_wait_for_container`/`_publish_container` のシグネチャは保持し optional kwargs で連携トークン受け渡し対応（既存テスト互換）。
> - リトライ/二重投稿防止は Phase 2 で先行実装済み（Phase 4 は cron のみ残）。
> - 実機 IG 投稿はユーザーの Meta App + ngrok HTTPS 公開が必要（未実施）。

- [x] `app/routers/connections.py` に Meta OAuth 追加（`/meta/start` + `/meta/callback`、長期 page token + IG ビジネス ID を暗号化保存）
- [x] `app/services/instagram.py` を connection ベースへ改修（`publish_to_instagram_with` + Meta OAuth helpers + fetch_permalink、env フォールバック維持）
- [x] `publisher.py` に instagram 分岐（connection 優先 / env フォールバック / HTTPS PUBLIC_BASE_URL 要求 / permalink 取得）
- [x] フロント: Instagram 接続ボタン（`/post/connections` に IG カード追加）
- [x] テスト: instagram publish 成功（connection）/ env フォールバック / 未連携不可 / HTTPS 必須 / 失敗記録 / Meta callback 保存 → 9 件追加で全 45 件 pass
- [x] ブラウザ検証: IG カード表示・接続ボタン → 未設定エラー表示
- [ ] 実機: ngrok トンネルで公開 → IG Reels に今すぐ投稿して permalink 保存を確認（**要 Meta App + ngrok**、ユーザー対応待ち）

## Phase 4: 予約実行 + リトライ + 二重投稿防止 + 履歴

- [ ] APScheduler をアプリ lifespan で 1 分間隔起動 → `publisher.run_due_posts()`
- [ ] `publisher.run_due_posts()`: `status='scheduled' AND scheduled_at<=now()` を `FOR UPDATE SKIP LOCKED` で取得 → atomic claim → 投稿
- [ ] `app/routers/cron.py`: `POST /api/cron/run`（`CRON_SECRET` 必須、手動/外部トリガー）
- [ ] リトライ: `POST /api/posts/{post_id}/retry`（retry_count+1 → posting → 再投稿）
- [ ] 投稿履歴: scheduled_posts の状態遷移を詳細画面に表示（status / posted_at / error_message / retry_count）
- [ ] テスト: 二重投稿防止（同一 post を並行 claim → 1 回のみ投稿）/ due 取得 / リトライ
- [ ] 実機: 予約日時到来で IG / YT に自動投稿されることを確認

## Phase 5: 仕上げ + commit

- [ ] README に投稿機能・ngrok 前提・OAuth 設定手順を追記
- [ ] backend 全テスト pass / frontend build pass
- [ ] commit（`feat: 投稿機能追加 (social-publishing)`）
- [ ] `openspec archive add-social-publishing`

## Out of Scope（将来別 change）
- AI キャプション生成（要件定義書 §12）
- 投稿テンプレート / 複製投稿 / 簡易分析（要件定義書 Phase 5）
- 複数アカウント管理 / TikTok 自動投稿
