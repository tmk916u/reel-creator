## Phase 1: 基盤 + UI + 予約保存（投稿実行なし）

### 1.1 DB / インフラ基盤
- [ ] `docker-compose.yml` に `db`（Postgres）サービス + `media-storage` volume を追加
- [ ] `requirements.txt` に `sqlalchemy` `alembic` `psycopg2-binary` `apscheduler` `cryptography` を追加
- [ ] `app/db.py`（engine / SessionLocal / Base / get_db 依存）
- [ ] `app/models/db_models.py`（videos / scheduled_posts / social_connections）
- [ ] Alembic 初期化 + 初回マイグレーション（3 テーブル）
- [ ] `.env.example` を投稿系 env（DATABASE_URL / PUBLIC_BASE_URL / META_* / GOOGLE_* / CRON_SECRET / TOKEN_ENCRYPTION_KEY）に更新

### 1.2 バックエンド（投稿 CRUD + アップロード）
- [ ] `app/models/schemas.py` に投稿系 Pydantic（VideoCreate / PostCreate / PostUpdate / PostOut 等）
- [ ] `app/services/storage.py`（media volume への保存 + サムネ抽出 = ffmpeg 1 フレーム）
- [ ] `app/services/hashtags.py`（正規化: 空白除去 / `#` 補完 / 6 個以上エラー）
- [ ] `app/routers/posts.py`:
  - `POST /api/posts/upload`（MP4 アップロード → videos 作成）
  - `POST /api/posts`（video + IG/YT scheduled_posts 作成、バリデーション D8）
  - `GET /api/posts`（一覧）/ `GET /api/posts/{id}`（詳細）
  - `PATCH /api/posts/{id}` / `DELETE /api/posts/{id}`
  - `GET /api/posts/media/{video_id}`（FileResponse 配信）
- [ ] `app/main.py` にルーター登録 + DB lifespan
- [ ] テスト（`tests/test_posts.py`）: アップロード / 作成バリデーション / ハッシュタグ正規化 / 一覧・詳細

### 1.3 フロントエンド（トップ分割 + 一覧 + 作成）
- [ ] 既存 `app/page.tsx` を `app/edit/page.tsx` へ移設（編集ロジック無変更）
- [ ] `app/page.tsx` を「編集する / 投稿する」導線のトップに差し替え
- [ ] `app/post/page.tsx`（一覧: サムネ / テーマ / 予定日時 / IG・YT ステータス / 操作ボタン）
- [ ] `app/post/new/page.tsx`（アップロード → プレビュー → テーマ → IG 設定 → YT 設定 → 予約 → 保存）
- [ ] `app/post/[id]/page.tsx`（詳細: プレビュー / 投稿内容 / 予約状況 / 履歴 / エラー）
- [ ] `lib/api.ts` に投稿系クライアント追加
- [ ] frontend type check / build pass

### 1.4 Phase 1 検証
- [ ] docker compose up で全サービス起動
- [ ] MP4 アップロード → IG/YT 予約を保存 → 一覧・詳細で確認（ブラウザ）
- [ ] backend テスト全 pass

## Phase 2: YouTube 投稿

- [ ] `app/services/crypto.py`（Fernet トークン暗号化）
- [ ] `app/routers/connections.py`: Google OAuth（認可開始 / コールバック → refresh_token を `social_connections` に暗号化保存）
- [ ] `app/services/youtube.py`: refresh_token → access_token、`videos.insert`（snippet / status.privacyStatus）、成功 URL 取得
- [ ] `app/services/publisher.py`（基礎）: 単一 scheduled_post を claim → platform 投稿 → ステータス更新
- [ ] `routers/posts.py` に `POST /api/posts/{post_id}/publish_now`
- [ ] フロント: 連携設定 UI（YouTube 接続ボタン）+ 「今すぐ投稿」ボタン
- [ ] テスト: OAuth コールバック保存 / youtube publish（mock）/ claim 冪等性
- [ ] 実機: 1 本を YouTube に今すぐ投稿して URL 保存を確認

## Phase 3: Instagram 投稿

- [ ] `app/routers/connections.py` に Meta OAuth 追加（長期トークン + IG ビジネス ID 保存）
- [ ] `app/services/instagram.py` を connection ベースへ改修（env フォールバック維持）
- [ ] `publisher.py` に instagram 分岐（公開 URL = `{PUBLIC_BASE_URL}/api/posts/media/{video_id}`）
- [ ] フロント: Instagram 接続ボタン
- [ ] テスト: instagram publish（mock）/ connection 未設定時の投稿不可
- [ ] 実機: ngrok トンネルで公開 → IG Reels に今すぐ投稿して permalink 保存を確認

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
