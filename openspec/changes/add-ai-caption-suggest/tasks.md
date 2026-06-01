## Phase 1: バックエンド

### 1.1 services/captions_ai.py 新規
- [x] 動画 → 音声抽出（`services/ffmpeg.extract_audio` 流用）
- [x] ReazonSpeech で書き起こし（`services/asr.py` の関数流用）
- [x] 既存 `services/llm.py` で Anthropic Claude にプロンプト送信
- [x] 出力 JSON を Pydantic で検証、不正なら例外
- [x] ハッシュタグは `services/hashtags.normalize_hashtags` を通す
- [x] エラーハンドリング: ASR / LLM の例外を個別に判別

### 1.2 スキーマ追加
- [x] `models/schemas.py` に以下追加:
  - `CaptionSuggestionRequest`: `{theme?: str}`
  - `CaptionSuggestionResponse`: `{instagram_caption, youtube_title, youtube_description, hashtags, cover_text_candidates}`

### 1.3 ルーター追加
- [x] `routers/posts.py` に `POST /api/posts/{video_id}/suggest` 実装
  - 404: 動画なし
  - 422: 書き起こし失敗
  - 502: LLM 失敗

### 1.4 テスト
- [x] `tests/test_captions_ai.py`（新規）:
  - LLM レスポンス（JSON）のパースと検証
  - 不正 JSON → エラー
  - ハッシュタグ正規化が効く
- [x] `tests/test_posts.py` に suggest エンドポイントのテスト追加（ASR / LLM mock）:
  - 404（動画なし）
  - 正常レスポンスの形
  - ASR エラー → 422
  - LLM エラー → 502
- [x] 既存 50 件 + 新規 5〜8 件で全 pass

## Phase 2: フロントエンド

### 2.1 API クライアント
- [x] `lib/api.ts` に追加:
  - `CaptionSuggestion` interface
  - `suggestCaptions(videoId: string, theme?: string): Promise<CaptionSuggestion>`

### 2.2 /post/new ページ更新
- [x] 動画アップロード完了後に「**✨ AI でキャプション生成**」ボタン表示
- [x] 押下 → ローディング状態（テキスト「書き起こし中…」→「AI 生成中…」など）
- [x] レスポンス受信 → 各フォーム欄に流し込む（IG キャプション / YT タイトル / YT 説明文 / ハッシュタグ）
- [x] 「**カバー文字案**」セクションを新設、3 案をカード表示、コピーボタン付き
- [x] エラー時は赤バナーで表示
- [x] 「再生成」ボタンで何度でも生成可能

### 2.3 検証
- [x] frontend tsc クリーン
- [x] frontend eslint クリーン

## Phase 3: 検証 + commit

- [x] backend 全テスト pass
- [x] dev backend 再起動 → ブラウザで実機検証:
  - 1 本の動画アップロード
  - 「AI でキャプション生成」クリック
  - サジェスト結果がフォームに反映される
  - 「カバー文字案」3 案が表示される
  - 編集して保存できる
- [x] commit（`feat: AI キャプション生成 (ai-caption-suggest)`）
- [x] `openspec archive add-ai-caption-suggest`

## Out of Scope（将来別 change）
- サムネ画像の自動生成（フレーム抽出 + 文字オーバーレイ合成）
- IG Reels `thumb_offset` の自動選択
- バズスコア再計算 / 投稿テンプレ
- 多言語対応
- 非同期ジョブ化 / プログレス WebSocket
