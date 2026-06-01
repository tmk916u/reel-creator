## Why

現状の Instagram 投稿は **Reels のみ**。Stories へも同じ動画を投稿できれば、Reels への導線として活用できる（Stories は 24h で消えるが視認性高く、Reels プロフィール訪問促進に有効）。Meta Graph API は同じ `POST /{ig_user_id}/media` で `media_type=STORIES` 指定すれば動画 Stories 投稿が可能で、既存実装の拡張だけで対応できる。

ユーザー要望: 1 つの投稿予約で **Reels だけ / Stories だけ / 両方** を独立に選べるようにしたい。

## What Changes

Instagram の投稿先として Reels と Stories を独立に選択可能にする。1 つの `scheduled_post`（platform=instagram）に Reels / Stories の On/Off フラグを持たせ、選択された media type すべてを順次投稿する。

### DB スキーマ
- `scheduled_posts` に列追加:
  - `instagram_to_reels: bool DEFAULT TRUE`
  - `instagram_to_stories: bool DEFAULT FALSE`
  - `stories_posted_at: timestamp NULL` （Stories の投稿時刻、永続 URL を持たないため URL ではなく時刻で記録）

### Backend
- `services/instagram.py`:
  - `publish_story_with(video_url, *, access_token, ig_account_id) -> dict` を追加
  - 内部的に `_ig_create_container(media_type="STORIES")` 系の小ヘルパー追加
- `services/publisher.py`:
  - `_publish_instagram`: scheduled_post の `instagram_to_reels` / `instagram_to_stories` を読み、選ばれた targets を反復投稿
  - すべて成功 → status=`posted` / Reels の permalink を `posted_url` / Stories の時刻を `stories_posted_at`
  - いずれか失敗 → status=`failed` + error_message に失敗内訳を記録
  - 両 OFF → 不正状態（バリデーションで弾く）
- `models/schemas.py`:
  - `PostCreate`: `instagram_to_reels: bool = True`, `instagram_to_stories: bool = False`
  - `PostUpdate`: 同じく更新可
  - `ScheduledPostOut`: 両フラグ + `stories_posted_at` を出力
- `routers/posts.py`:
  - 作成時バリデーション: `post_to_instagram=True` なら最低 1 つの IG target が必要

### Frontend
- `/post/new` の Instagram セクション:
  - 親「Instagram に投稿」ON のとき、子チェックボックス 2 つ表示:
    - ☑ Reels（デフォルト ON）
    - ☐ Stories（デフォルト OFF）
  - 両方 OFF だと予約保存ブロック
- `/post/[id]` 詳細:
  - Instagram カードに「Reels: 投稿済 / 未投稿」「Stories: 投稿済（時刻）」の小ステータス表示

### Out of Scope（将来別 change）
- Stories と Reels で**異なる予約日時**を持つ（今は同じ scheduled_at で両方投稿）
- Stories 用のテキスト・ステッカー等のオーバーレイ API 利用（API スコープ外）
- 写真（image_url）Stories 投稿（今は動画のみ）

- BREAKING: なし（既存 `scheduled_posts` レコードはマイグレーションで `instagram_to_reels=true, instagram_to_stories=false` のデフォルト値で初期化）

## Capabilities

### Modified Capabilities
- `social-publishing`: Instagram Stories 投稿対応（ADDED Requirements）

## Impact

- **DB**: `scheduled_posts` に 2 bool + 1 timestamp カラム追加。create_all で自動付与 / 既存データはデフォルト値で互換
- **Backend**: instagram.py / publisher.py / schemas.py / posts.py に拡張、新規行 ~80 行
- **Frontend**: /post/new と /post/[id] にサブチェックボックスとステータス表示、~40 行
- **テスト**: instagram.py の Stories 投稿成功 / publisher の 両方/片方/エラー パターン / バリデーション、~8 件
- **処理時間**: Reels + Stories 両方選択時は順次投稿（IG のコンテナ処理 10〜60 秒 × 2）
- **コスト**: なし（既存 IG API クォータ内）
