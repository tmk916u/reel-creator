## ADDED Requirements

### Requirement: アプリ入口の分割

システムはトップ画面で「編集」と「投稿」の 2 つの導線を提供する SHALL。既存の編集ウィザードは `/edit` に配置し、投稿機能は `/post` 配下に配置する。

#### Scenario: トップ画面の導線
- **WHEN** ユーザーが `/` にアクセスした
- **THEN** 「編集する」（`/edit` へ）と「投稿する」（`/post` へ）の 2 つの導線が表示される

#### Scenario: 編集機能の移設
- **WHEN** ユーザーが `/edit` にアクセスした
- **THEN** 既存の動画編集ウィザード（無音削除・字幕生成）がロジック変更なく動作する

### Requirement: 動画のアップロード

システムは完成済み MP4 動画をアップロードして `videos` レコードを作成する SHALL。アップロードした動画はローカルストレージに保存し、`storage_path` と `file_url` を記録する。

#### Scenario: MP4 アップロード成功
- **WHEN** ユーザーが MP4 ファイルを `POST /api/posts/upload` にアップロードした
- **THEN** ファイルが media ストレージに保存され、`videos` レコード（id / file_url / storage_path / original_filename / thumbnail_url）が作成される

#### Scenario: 非 MP4 の拒否
- **WHEN** MP4 以外、またはファイルサイズ上限を超える動画がアップロードされた
- **THEN** バリデーションエラーを返し、レコードは作成されない

#### Scenario: サムネイル生成
- **WHEN** 動画アップロードが成功した
- **THEN** ffmpeg で 1 フレームを抽出してサムネイルを生成し、`thumbnail_url` に記録する

### Requirement: 投稿の作成とバリデーション

システムは 1 本の動画に対し Instagram 用・YouTube 用の `scheduled_posts` を**別レコード**として作成する SHALL。投稿予定日時は JST で扱い、媒体ごとに別日時を指定できる。

入力項目: テーマ / Instagram キャプション / YouTube タイトル / YouTube 説明文 / ハッシュタグ / IG 投稿有無 / YT 投稿有無 / IG 予約日時 / YT 予約日時 / 公開設定 / メモ。

#### Scenario: 両媒体に予約作成
- **WHEN** IG ON・YT ON で、IG 予約日時と YT 予約日時（別日時可）を指定して `POST /api/posts` が呼ばれた
- **THEN** `videos` 1 件と、platform が instagram / youtube の `scheduled_posts` 2 件が status=`scheduled` で作成される

#### Scenario: 両媒体 OFF は保存不可
- **WHEN** IG OFF かつ YT OFF で投稿作成が呼ばれた
- **THEN** バリデーションエラーを返し、レコードは作成されない

#### Scenario: Instagram 必須項目
- **WHEN** IG ON だが Instagram キャプションが空、または IG 予約日時が未指定
- **THEN** バリデーションエラーを返す

#### Scenario: YouTube 必須項目
- **WHEN** YT ON だが YouTube タイトルまたは説明文が空、または YT 予約日時が未指定
- **THEN** バリデーションエラーを返す

#### Scenario: 連携未設定の媒体は投稿不可
- **WHEN** IG ON だが instagram の `social_connections` が未設定（または is_active=false）
- **THEN** バリデーションエラーを返し、その媒体への予約は作成されない

#### Scenario: 過去日時の警告
- **WHEN** 予約日時に現在より過去の日時が指定された
- **THEN** 警告を返し、「今すぐ投稿」として扱うかをユーザーに確認する

#### Scenario: 投稿済みは編集不可
- **WHEN** status=`posted` の `scheduled_posts` を編集しようとした
- **THEN** 編集は拒否され、複製して新規作成するよう促す

### Requirement: ハッシュタグの正規化

システムは各媒体最大 5 個のハッシュタグを受け付け、保存時に正規化する SHALL。スペース区切り・改行区切りの両方を受け付ける。

#### Scenario: 正規化
- **WHEN** `ダイエット 食事改善` のように `#` なしスペース区切りで入力された
- **THEN** 空白を除去し各語の先頭に `#` を補完して `#ダイエット #食事改善` として保存する

#### Scenario: 6 個以上はエラー
- **WHEN** 6 個以上のハッシュタグが入力された
- **THEN** バリデーションエラーを返す

### Requirement: 投稿一覧

システムは `/post` で投稿一覧を表示する SHALL。表示項目: サムネイル / テーマ / 投稿予定日時 / Instagram ステータス / YouTube ステータス / 作成日 / 投稿済み URL / 編集・今すぐ投稿・リトライ・削除の操作。

#### Scenario: 一覧表示
- **WHEN** ユーザーが `/post` にアクセスした
- **THEN** 各動画のサムネ・テーマ・媒体別ステータス・予定日時・操作ボタンが一覧表示される

### Requirement: 投稿詳細

システムは `/post/[id]` で投稿詳細を表示する SHALL。表示項目: 動画プレビュー / 投稿情報 / Instagram 投稿内容 / YouTube 投稿内容 / 予約状況 / 投稿履歴 / API レスポンス概要 / エラーメッセージ / リトライボタン。

#### Scenario: 詳細表示
- **WHEN** ユーザーが `/post/{id}` にアクセスした
- **THEN** 動画プレビュー・媒体別投稿内容・予約状況・履歴（status / posted_at / error_message / retry_count）が表示される

### Requirement: データモデル

システムは `videos` / `scheduled_posts` / `social_connections` の 3 テーブルを Postgres に持つ SHALL。

- `videos`: id(uuid) / file_url / storage_path / original_filename / thumbnail_url / duration_seconds / aspect_ratio / theme / memo / created_at / updated_at
- `scheduled_posts`: id(uuid) / video_id(FK) / platform / scheduled_at / status / caption / title / description / hashtags / privacy_status / posted_url / external_post_id / error_message / retry_count / posted_at / created_at / updated_at
- `social_connections`: id(uuid) / platform / account_name / external_account_id / access_token / refresh_token / token_expires_at / is_active / created_at / updated_at

#### Scenario: status の値域
- **WHEN** `scheduled_posts.status` を設定する
- **THEN** `draft` / `scheduled` / `posting` / `posted` / `failed` / `cancelled` のいずれかである

### Requirement: SNS アカウントの OAuth 連携

システムは Instagram / YouTube のアカウントを OAuth で連携し、トークンを暗号化して `social_connections` に保存する SHALL。env 変数へのベタ書きには依存しない。

#### Scenario: YouTube 連携
- **WHEN** ユーザーが YouTube 接続を開始し Google OAuth の認可を完了した
- **THEN** refresh_token を含む連携情報が暗号化されて `social_connections`（platform=youtube, is_active=true）に保存される

#### Scenario: Instagram 連携
- **WHEN** ユーザーが Instagram 接続を開始し Meta OAuth の認可を完了した
- **THEN** 長期アクセストークンと IG ビジネスアカウント ID が暗号化されて `social_connections`（platform=instagram, is_active=true）に保存される

#### Scenario: トークン暗号化
- **WHEN** access_token / refresh_token を DB に保存する
- **THEN** `TOKEN_ENCRYPTION_KEY` を用いた暗号化（Fernet）後の値が保存され、平文では保存されない

### Requirement: YouTube Shorts 投稿

システムは `videos.insert` で YouTube に動画をアップロードする SHALL。snippet.title / description（+ハッシュタグ）/ status.privacyStatus を設定し、成功後に動画 URL を保存する。MVP の既定 privacyStatus は `public`。

#### Scenario: YouTube 投稿成功
- **WHEN** platform=youtube の投稿が実行され、有効な連携が存在する
- **THEN** refresh_token から access_token を取得し videos.insert を実行、status=`posted`・posted_url（`https://youtu.be/{id}`）・external_post_id・posted_at が保存される

#### Scenario: 公開設定
- **WHEN** privacy_status に public / private / unlisted のいずれかが指定された
- **THEN** その値が status.privacyStatus に設定される

### Requirement: Instagram Reels 投稿

システムは Instagram Graph API で Reels を投稿する SHALL。media_type=REELS でメディアコンテナを作成 → 処理状態をポーリング → publish し、permalink または投稿 ID を保存する。video_url は外部からアクセス可能な HTTPS URL を渡す。

#### Scenario: Instagram 投稿成功
- **WHEN** platform=instagram の投稿が実行され、有効な連携が存在する
- **THEN** `{PUBLIC_BASE_URL}/api/posts/media/{video_id}` を video_url として REELS コンテナを作成し、FINISHED 後に publish、status=`posted`・posted_url・external_post_id・posted_at が保存される

#### Scenario: 公開 URL（ローカル Docker）
- **WHEN** ローカル Docker で Instagram 投稿を行う
- **THEN** ngrok 等のトンネルで公開された `PUBLIC_BASE_URL` 経由で動画が Instagram から取得可能である必要がある（短命の署名 URL は使わない）

#### Scenario: Instagram 投稿失敗
- **WHEN** コンテナ処理が ERROR・タイムアウト・publish 失敗のいずれかになった
- **THEN** status=`failed` とし API レスポンス概要を error_message に保存する

### Requirement: メディア配信エンドポイント

システムはアップロード動画を HTTP 配信するエンドポイントを提供する SHALL（Instagram API が動画 URL を取得するために使用）。

#### Scenario: 動画配信
- **WHEN** `GET /api/posts/media/{video_id}` が呼ばれ、対象動画が存在する
- **THEN** `video/mp4` の FileResponse を返す

### Requirement: 予約実行（cron）

システムは 1 分間隔のスケジューラで予約投稿を実行する SHALL。`status='scheduled'` かつ `scheduled_at <= now()` のレコードを対象に、platform に応じた投稿処理を行う。`CRON_SECRET` で保護した手動トリガーエンドポイントも提供する。

#### Scenario: 予約到来で自動投稿
- **WHEN** scheduled_at が現在時刻を過ぎた status=`scheduled` のレコードが存在する
- **THEN** スケジューラが対象を取得して投稿を実行し、結果に応じて status を `posted` / `failed` に更新する

#### Scenario: 手動トリガーの保護
- **WHEN** `POST /api/cron/run` が `CRON_SECRET` なし、または不一致で呼ばれた
- **THEN** 401 を返し、予約実行は行わない

### Requirement: 二重投稿の防止

システムは同一の予約投稿が二重投稿されないよう排他制御を行う SHALL。`posting` への遷移は atomic な条件付き更新で行い、取得済みの行は他プロセスが取得しない。

#### Scenario: atomic claim
- **WHEN** あるレコードを投稿実行する直前
- **THEN** `UPDATE scheduled_posts SET status='posting' WHERE id=:id AND status IN ('scheduled','failed') RETURNING id` を実行し、更新行数が 1 のときのみ投稿を実行する

#### Scenario: 並行実行での重複防止
- **WHEN** cron 実行と「今すぐ投稿」が同一レコードに同時に走った
- **THEN** claim に成功するのは一方のみで、投稿は 1 回だけ実行される

#### Scenario: posted の再投稿禁止
- **WHEN** status=`posted` のレコードに対して投稿が要求された
- **THEN** claim 条件を満たさないため再投稿されない

### Requirement: 今すぐ投稿

システムは一覧・詳細画面から対象の予約投稿を即時実行できる SHALL。

#### Scenario: 今すぐ投稿
- **WHEN** ユーザーが `POST /api/posts/{post_id}/publish_now` を呼んだ（対象が scheduled または failed）
- **THEN** 二重投稿防止の claim を通して即時投稿し、結果を保存する

### Requirement: 手動リトライ

システムは `failed` になった投稿を手動でリトライできる SHALL。

#### Scenario: リトライ
- **WHEN** status=`failed` のレコードに対し `POST /api/posts/{post_id}/retry` が呼ばれた
- **THEN** retry_count を +1 し status を `posting` に遷移して再投稿、結果に応じて `posted` / `failed` を保存する
