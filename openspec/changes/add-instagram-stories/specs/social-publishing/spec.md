## ADDED Requirements

### Requirement: Instagram の投稿先選択

システムは Instagram 投稿の対象として **Reels** と **Stories** を独立に選択可能にする SHALL。1 つの予約レコードで両方・片方・全 OFF を表現する。

#### Scenario: デフォルトは Reels のみ
- **WHEN** ユーザーが `/post/new` で「Instagram に投稿」をオンにする
- **THEN** Reels は ON、Stories は OFF のデフォルトでフォームに反映される

#### Scenario: Reels のみ選択して保存
- **WHEN** `instagram_to_reels=true`, `instagram_to_stories=false` で `POST /api/posts` が呼ばれた
- **THEN** scheduled_post.platform=instagram のレコードが作られ、両フラグが保存される

#### Scenario: 両方選択して保存
- **WHEN** `instagram_to_reels=true`, `instagram_to_stories=true` で投稿予約を作成
- **THEN** 1 つの scheduled_post（platform=instagram）に両フラグが立った状態で保存される

#### Scenario: 両 OFF はバリデーションエラー
- **WHEN** `post_to_instagram=true` で `instagram_to_reels=false` かつ `instagram_to_stories=false`
- **THEN** 422 を返し、保存しない

### Requirement: Stories 投稿の API 仕様

システムは Instagram Stories 投稿に **Instagram Graph API** の `media_type=STORIES` を使用する SHALL。

#### Scenario: Stories 投稿成功
- **WHEN** scheduled_post に `instagram_to_stories=true` があり、投稿が実行された
- **THEN** `POST graph.instagram.com/v23.0/{ig_user_id}/media` を `media_type=STORIES` + `video_url` で呼び出し、コンテナ status をポーリングし、`media_publish` で公開する

#### Scenario: Stories は permalink を取得しない
- **WHEN** Stories 投稿が成功した
- **THEN** `stories_posted_at` に投稿時刻を記録する（Stories は 24h で消えるため `posted_url` には記録しない）

### Requirement: Reels と Stories の同時投稿

両方選択時は **Reels → Stories の順**で投稿し、すべて成功して初めて `posted` ステータスとする SHALL。

#### Scenario: 両方成功
- **WHEN** `instagram_to_reels=true` かつ `instagram_to_stories=true` の post が実行された
- **THEN** Reels を先に投稿してその permalink を `posted_url` に、Stories を続けて投稿してその時刻を `stories_posted_at` に記録し、status=`posted`

#### Scenario: Reels 失敗時は Stories をスキップ
- **WHEN** Reels 投稿で API エラーが発生した
- **THEN** Stories 投稿はスキップし、status=`failed` で `error_message` に Reels 失敗内容を記録

#### Scenario: Reels 成功 + Stories 失敗
- **WHEN** Reels は成功したが Stories で API エラーが発生した
- **THEN** status=`failed`、`posted_url` には Reels の permalink が入り、`error_message` に Stories の失敗内容を記録

#### Scenario: 片方のみ選択
- **WHEN** `instagram_to_reels=true`, `instagram_to_stories=false`（または逆）の場合
- **THEN** 選択された 1 つだけを投稿し、成功なら status=`posted`、失敗なら `failed`

### Requirement: 詳細画面のステータス表示

`/post/[id]` の Instagram カードは Reels と Stories の投稿状態を区別して表示する SHALL。

#### Scenario: Reels 投稿済み Stories 投稿済み
- **WHEN** scheduled_post が両方成功している
- **THEN** Instagram カードに「Reels: 投稿済（permalink リンク）」「Stories: 投稿済（時刻）」を表示

#### Scenario: Reels のみ対象（Stories 非選択）
- **WHEN** `instagram_to_stories=false`
- **THEN** Stories の行は「対象外」表示にするか、または非表示にする
