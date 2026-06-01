## Context

### 既存実装
- `social-publishing` capability で IG Reels 投稿は確立済み（Instagram Login flow + graph.instagram.com）
- `instagram.py` に `publish_to_instagram_with()` + 内部 `_ig_create_container / _ig_wait_for_container / _ig_publish_container`
- `_ig_create_container` は `media_type="REELS"` をハードコード

### Stories と Reels の API 差
- 投稿エンドポイント: 同じ `POST /{ig_user_id}/media`
- 差は `media_type` パラメータ: `"REELS"` vs `"STORIES"`
- Stories 動画仕様: 最大 60 秒・9:16・100MB（Reels と同等）
- 公開後の差: Reels は permalink（永続）、Stories は 24h で消える（permalink 取得不可ではないが価値薄）

## Goals / Non-Goals

**Goals:**
- 1 つの投稿予約で Reels / Stories / 両方を独立選択可能にする
- 両方選択時は同じ scheduled_at で順次投稿
- どちらか失敗時はステータスを `failed` にして再試行可能にする

**Non-Goals:**
- Stories と Reels で異なる予約日時（将来別 change）
- Stories 専用のテキスト・ステッカー等
- 写真（image_url）Stories（動画のみ）
- 複数 Stories（カルーセル）

## Decisions

### D1: DB 設計は単一行 + 2 bool フラグ
- `scheduled_posts` 1 行（platform=instagram）に Reels / Stories の On/Off を持たせる
- 別行に分けない（独立スケジュール不要のため）

### D2: 投稿順序は Reels → Stories
- 失敗時に Reels が優先される（永続的に意味があるのは Reels）
- Reels 失敗時は Stories はスキップ（status=failed）
- Reels 成功 + Stories 失敗 → 全体 status=failed（リトライで両方再投稿、ただし Reels は重複ガード）

#### Scenario: 重複ガード（リトライ時）
- 失敗状態のレコードでも `posted_url` が既にあれば Reels は再投稿スキップ、Stories だけ実行
- 現状 publisher は claim → 一括処理なので、内部で「すでに posted の target はスキップ」のチェックを足す

実装シンプル化のため初版は **全 target を再投稿**（idempotent ではなく at-least-once）とし、複雑になりそうなら別 change で精緻化。

### D3: Stories の permalink は取得しない
- `posted_url` には Reels の permalink のみ
- Stories の投稿成功は `stories_posted_at` 時刻で記録（True/False 代わりに時刻 NOT NULL で投稿済みフラグとする）

### D4: バリデーション
- `post_to_instagram=True` AND `instagram_to_reels=False` AND `instagram_to_stories=False` → 422
- どちらか 1 つ以上必須

### D5: UI
- 親「Instagram に投稿」ON のときだけ子チェックボックスを表示
- 子のデフォルトは Reels=ON, Stories=OFF（Reels 中心の運用前提）
- 両 OFF にした瞬間に警告

### D6: マイグレーション
- 既存運用は IG 投稿レコードが少数（運用テスト程度）
- `create_all` での自動カラム追加で済む（SQLAlchemy 2.0 + sqlite/postgres 両対応）
- ただし `create_all` は既存テーブルにカラム追加しないので、開発時のみ手動 ALTER（または DB を空にする）が必要。本番運用に入る前なら DB 空で問題なし。
- Alembic 導入は引き続き保留（次回スキーマ変更が増えたら検討）

## Risks / Trade-offs

### R1: 既存 DB のカラム不足
**Mitigation**: 開発中の Postgres は DROP/CREATE で OK。本番運用に入る前なら影響軽微。実装時に注意点として記載。

### R2: Stories の動画仕様違反（60 秒超 / 100MB 超）
**Mitigation**: Meta API が 422 / ERROR で返すので、その error_message を保存して終了。フロント側で事前警告は将来別 change。

### R3: Reels だけ成功 / Stories だけ失敗 のリトライで重複投稿
**Mitigation**: 初版は at-least-once（再投稿される）。Stories は 24h で消えるので重複コストは限定的。Reels の重複は注意。将来 idempotent 化を検討。

### R4: scheduled_at 共有による柔軟性低下
**Mitigation**: 両方同時に投稿したいケースが大半。異なる時刻が必要なら現状でも別 video アップロード + 別予約で対応可。

## Migration Plan

### Phase 1: Backend
1. DB 列追加: `scheduled_posts` に `instagram_to_reels`, `instagram_to_stories`, `stories_posted_at`
   - 既存ローカル DB は手動 ALTER または DROP/CREATE
2. `instagram.py`:
   - `_ig_create_container` に `media_type` 引数追加（デフォルト "REELS"）
   - `publish_story_with()` 追加（実体は `publish_to_instagram_with` + `media_type=STORIES`、permalink fetch 省略）
3. `publisher.py._publish_instagram`:
   - 選択された targets を反復実行
   - Reels 成功時 `posted_url` 記録、Stories 成功時 `stories_posted_at` 記録
   - エラー集約
4. `schemas.py`: PostCreate/Update に 2 bool 追加、ScheduledPostOut に 2 bool + stories_posted_at 追加
5. `routers/posts.py`: create 時バリデーション（IG ON で両 OFF を拒否）

### Phase 2: Frontend
1. `lib/api.ts`: PostCreatePayload / ScheduledPost に新フィールド追加
2. `/post/new`: 親 IG トグル ON のとき Reels/Stories の子チェック表示
3. `/post/[id]`: PlatformCard の Instagram 側に「Reels: 投稿済/未投稿」「Stories: 投稿済」の小ステータス

### Phase 3: テスト + 検証 + commit + archive
- instagram.py: publish_story の mock テスト
- publisher: 両方成功 / Reels だけ / Stories だけ / 両 OFF（バリデーション）/ 部分失敗
- フロント: tsc / eslint
- 実機: ngrok 経由で `@ichiki_kuukan` に Reels+Stories 同時投稿確認
- commit + `openspec archive add-instagram-stories`

### Rollback
- 新カラムは NULL/false で害なし
- 古いコードでも `instagram_to_reels` が無いと NULL = false 扱いで投稿スキップになる懸念があるので、デフォルト true で初期化
- git revert で完全に戻る
