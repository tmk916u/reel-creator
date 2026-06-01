## ADDED Requirements

### Requirement: AI キャプション生成エンドポイント

システムは動画から音声を書き起こし、LLM を用いて投稿用テキスト一式を生成するエンドポイントを提供する SHALL。

ASR には ReazonSpeech、LLM には Anthropic Claude を使用する（既存サービスを流用）。

#### Scenario: 正常生成
- **WHEN** `POST /api/posts/{video_id}/suggest` が、存在する `video_id` に対して呼ばれた
- **THEN** 動画から音声を抽出 → ReazonSpeech で書き起こし → LLM で構造化生成 → `CaptionSuggestionResponse` を返す

#### Scenario: video が存在しない
- **WHEN** 存在しない `video_id` で呼ばれた
- **THEN** 404 を返す

#### Scenario: 書き起こし失敗
- **WHEN** ASR がエラーになった、または書き起こし結果が空
- **THEN** 422 を返し、メッセージに「書き起こしに失敗しました」を含める

#### Scenario: LLM 失敗
- **WHEN** LLM API がエラーを返す / タイムアウトする / JSON 解析に失敗する
- **THEN** 502 を返し、メッセージに「AI 生成に失敗しました」を含める

### Requirement: 生成内容

システムは以下 5 種類の項目を JSON で同時に生成する SHALL。

- **instagram_caption** (string): 200 文字以内、ハッシュタグ含めない、絵文字適度
- **youtube_title** (string): 70 文字以内、クリック率を意識
- **youtube_description** (string): 500 文字以内、結論 → 詳細 → CTA の構造
- **hashtags** (string[]): 5 個、`#` 付き、各媒体共通で使えるもの
- **cover_text_candidates** (string[]): 3 案、各 7〜12 文字以内、強い訴求

#### Scenario: ハッシュタグ正規化
- **WHEN** LLM が `["ダイエット", "#食事改善", "ボディメイク"]` のような混在形式を返した
- **THEN** `services/hashtags.normalize_hashtags` を通して `["#ダイエット", "#食事改善", "#ボディメイク"]` に揃え、5 個を超えていればエラー

#### Scenario: テーマ指定がある場合
- **WHEN** リクエストボディに `theme` フィールドが含まれる
- **THEN** LLM のプロンプトにテーマを渡し、生成内容がテーマに沿うようにする

#### Scenario: テーマ指定がない場合
- **WHEN** `theme` がリクエストに含まれない
- **THEN** 書き起こしのみから生成する（テーマなしでも生成は成立する）

### Requirement: フロントエンドの統合

`/post/new` ページは、動画アップロード後に AI キャプション生成ボタンを表示し、結果をフォーム各欄に反映する SHALL。

#### Scenario: AI 生成ボタン表示
- **WHEN** ユーザーが `/post/new` で動画を 1 本アップロード完了した
- **THEN** プレビュー下に「✨ AI でキャプション生成」ボタンが表示される

#### Scenario: 生成中の UI
- **WHEN** ユーザーが AI 生成ボタンを押した
- **THEN** ボタンが無効化され、ローディング表示（「書き起こし中…」「AI 生成中…」等）が出る

#### Scenario: 生成結果の反映
- **WHEN** 生成が成功して結果が返ってきた
- **THEN** Instagram キャプション / YouTube タイトル / YouTube 説明文 / ハッシュタグの各フォーム欄に値が入る

#### Scenario: カバー文字案の表示
- **WHEN** 生成結果に `cover_text_candidates` が含まれる
- **THEN** 投稿フォーム下に「カバー文字案」セクションを表示し、3 案をカードで並べる。各カードに「コピー」ボタンがある

#### Scenario: 再生成
- **WHEN** ユーザーが生成結果に納得せず、もう一度ボタンを押した
- **THEN** 新しい生成リクエストが走り、結果が再度フォームに反映される（既存値は上書き）

#### Scenario: 生成失敗時の表示
- **WHEN** バックエンドが 422 / 502 を返した
- **THEN** フォーム値は変更されず、画面上部に赤バナーでエラーメッセージが表示される
