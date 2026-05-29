## Why

現状の reel-creator は「編集」（無音削除・AI 字幕）に特化した**ステートレスな動画処理 API** であり、投稿機能を持たない。

一方で実運用は次のフローに変わりつつある:

1. Edits 等で動画を編集する
2. TikTok で字幕を付ける
3. TikTok にはそのまま投稿する
4. TikTok から字幕付き（ウォーターマークなし）動画を保存する
5. **その完成動画を Instagram Reels / YouTube Shorts に投稿・予約投稿したい** ← ここが未実装

「字幕付け」は TikTok に任せる方針が固まったため、reel-creator の価値は **完成動画の予約投稿の自動化** に移る。アプリの入口を「編集」と「投稿」に分け、今回は **投稿側のみ** を新規 capability として追加する。

投稿頻度は 1 日 1 動画程度を想定。高負荷対応は不要だが、**二重投稿防止**と**失敗時のリトライ**は必須。

## What Changes

新 capability `social-publishing` を追加する。完成動画をアップロードし、Instagram Reels / YouTube Shorts へ予約投稿・即時投稿・リトライできるようにする。

### アーキテクチャ決定（要確認）
- **既存 FastAPI バックエンドを拡張**（Supabase / Vercel は採用しない）。実行環境が「ローカル Docker のみ」のため、スタックを Docker Compose 内に閉じる。
- **Postgres を docker-compose に追加**（SQLAlchemy + Alembic）。データモデルは uuid PK / timestamp で要件定義書に準拠。二重投稿防止は Postgres の atomic な `UPDATE ... RETURNING` / `FOR UPDATE SKIP LOCKED` で実現する。
- **SNS アカウントは OAuth で連携**し、トークンを `social_connections` に暗号化保存する（env 変数ベタ書きではない）。
- **動画ストレージはローカル Docker volume**。Instagram は公開 HTTPS URL を要求するため、投稿時は **ngrok 等のトンネル**で `PUBLIC_BASE_URL` を公開する前提とする。

### Backend（`backend/app`）
- DB 基盤: `db.py`（engine/session）、`models/db_models.py`（videos / scheduled_posts / social_connections）、Alembic マイグレーション
- ルーター: `routers/posts.py`（投稿 CRUD・アップロード・今すぐ投稿・リトライ・メディア配信）、`routers/connections.py`（OAuth 連携）、`routers/cron.py`（予約実行トリガー、`CRON_SECRET` 保護）
- サービス: `services/youtube.py`（新規: OAuth + `videos.insert`）、`services/instagram.py`（既存 Reels コードを connection ベースに適応）、`services/publisher.py`（予約実行ワーカー: 排他 claim → platform 投稿 → ステータス更新）、`services/crypto.py`（トークン暗号化 Fernet）
- スケジューラ: APScheduler をバックエンド内で 1〜5 分間隔起動し、`publisher` を呼ぶ（外部 cron 不要）。手動/外部トリガー用に保護エンドポイントも用意
- スキーマ: `models/schemas.py` に投稿系 Pydantic モデルを追加

### Frontend（`frontend/app`）
- トップ画面を「編集 / 投稿」の入口に分割。既存の編集ウィザード（現 `app/page.tsx`）を `/edit` へ移設し、`/` は導線チョイス画面にする（編集ロジックは無変更、ルートのみ移動）
- `/post`（一覧）、`/post/new`（作成）、`/post/[id]`（詳細）を App Router で追加
- `lib/api.ts` に投稿系 API クライアントを追加

### Infra
- `docker-compose.yml` に `db`（Postgres）サービスと media volume を追加
- `.env.example` を投稿系 env（DATABASE_URL / META_* / GOOGLE_* / CRON_SECRET / TOKEN_ENCRYPTION_KEY / PUBLIC_BASE_URL）に更新

- BREAKING: トップ画面の URL 構成変更（編集ウィザードが `/` → `/edit` へ移動）。編集機能のロジック自体は無変更。

## Capabilities

### Added Capabilities
- `social-publishing`: 完成動画のアップロード、Instagram Reels / YouTube Shorts への予約投稿・即時投稿・リトライ・ステータス管理・投稿履歴

## Impact

- **Backend**: 新規ルーター 3 / サービス 3 + DB 基盤 + Alembic。`requirements.txt` に `sqlalchemy` `alembic` `psycopg2-binary` `apscheduler` `cryptography` `google-api-python-client` `google-auth-oauthlib` を追加
- **Frontend**: 新規ページ 4（top/list/new/detail）+ API クライアント拡張。既存編集ページは `/edit` へ移設
- **Infra**: Postgres コンテナ 1 追加、media volume 1 追加
- **既存編集パイプライン**: 無変更（投稿は独立 capability。`video.py` / `subtitle.py` / `director.py` 等は触らない）
- **段階導入**: Phase 1（UI + DB + 予約保存、投稿実行なし）→ Phase 2（YouTube）→ Phase 3（Instagram）→ Phase 4（cron/リトライ/二重投稿防止/履歴）。AI キャプション生成（要件定義書 §12 / Phase 5）は **本 change の Non-Goal**（将来別 change）
