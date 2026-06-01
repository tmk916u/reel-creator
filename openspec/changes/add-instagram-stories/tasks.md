## Phase 1: Backend

### 1.1 DB スキーマ
- [ ] `models/db_models.py` の `ScheduledPost` に追加:
  - `instagram_to_reels: bool DEFAULT True`
  - `instagram_to_stories: bool DEFAULT False`
  - `stories_posted_at: datetime | None`
- [ ] 開発 Postgres DB は drop/recreate or 手動 ALTER（Alembic 不使用のため）

### 1.2 instagram.py
- [ ] `_ig_create_container` に `media_type: str = "REELS"` 引数追加
- [ ] `publish_story_with(video_url, *, access_token, ig_account_id) -> dict` 追加
  - 実体は Reels と同じフローで `media_type="STORIES"` を渡す
  - permalink 取得は省略（Stories は 24h で消えるため）

### 1.3 publisher.py
- [ ] `_publish_instagram` を target 反復に変更:
  - `instagram_to_reels` and `instagram_to_stories` を読む
  - 両方 OFF → エラー（バリデーション漏れの場合）
  - 順次投稿: Reels → Stories
  - すべて成功で `posted` / Reels 永続URL を `posted_url` / Stories 時刻を `stories_posted_at`
  - 失敗があれば `failed` + error_message に内訳

### 1.4 schemas.py
- [ ] `PostCreate`: `instagram_to_reels: bool = True`, `instagram_to_stories: bool = False`
- [ ] `PostUpdate`: 同上（Optional）
- [ ] `ScheduledPostOut`: `instagram_to_reels`, `instagram_to_stories`, `stories_posted_at` を追加

### 1.5 routers/posts.py バリデーション
- [ ] create / update: `post_to_instagram=True` で両 target OFF → 422

### 1.6 テスト
- [ ] `tests/test_instagram.py` に `publish_story_with` の mock テスト
- [ ] `tests/test_publisher.py` に追加:
  - 両方成功
  - Reels のみ ON で成功
  - Stories のみ ON で成功
  - Reels 失敗 → Stories スキップ → 全体 failed
  - 両 OFF → publisher エラー
- [ ] `tests/test_posts.py` に追加:
  - 両 OFF で create → 422
  - create 時のデフォルト値確認
- [ ] 既存 88 件 + 新規 8 件で全 pass

## Phase 2: Frontend

### 2.1 API client
- [ ] `lib/api.ts`:
  - `PostCreatePayload` に `instagram_to_reels?: bool`, `instagram_to_stories?: bool`
  - `ScheduledPost` に同フィールド + `stories_posted_at: string | null`

### 2.2 /post/new
- [ ] 親「Instagram に投稿」ON のときに子チェックボックス 2 つ表示
  - ☑ Reels（デフォルト ON）
  - ☐ Stories
- [ ] 両 OFF だと保存ボタン無効化 or 警告
- [ ] 送信時に payload に 2 フラグ追加

### 2.3 /post/[id]
- [ ] `PlatformCard` の Instagram 側を拡張:
  - Reels: 「投稿済（URL あり）」or「未投稿」
  - Stories: 「投稿済（時刻）」or「未投稿」or「対象外」

### 2.4 検証
- [ ] frontend tsc
- [ ] frontend eslint

## Phase 3: 検証 + commit + archive

- [ ] backend 全テスト pass
- [ ] dev backend 再起動 → ブラウザで実機:
  - Reels のみで投稿
  - Stories のみで投稿（24h で消えることを確認）
  - 両方で投稿
  - 両 OFF で保存できないこと
- [ ] commit（`feat: Instagram Stories 投稿対応 (add-instagram-stories)`）
- [ ] `openspec archive add-instagram-stories`

## Out of Scope（将来別 change）
- Reels と Stories で異なる予約日時
- Stories テキスト・ステッカー オーバーレイ
- 写真（image_url）Stories
- カルーセル Stories
- 重複投稿 idempotent ガード（リトライ時の Reels 二重投稿防止）
