## Context

### 既存資産の状況
- **ASR**: `backend/app/services/asr.py` に ReazonSpeech ベースの書き起こし実装あり。`whisperx` も pinned。編集パイプラインで稼働中で動画から文字起こしできる
- **LLM**: `backend/app/services/llm.py` に Anthropic / OpenAI 切替のクライアント実装あり。`LLM_PROVIDER=anthropic` で稼働中（編集パイプラインの言い直し検出・director 等で使用）
- **動画ストレージ**: `social-publishing` Phase 1 で `MEDIA_DIR/{video_id}/source.mp4` に保存している。`storage.source_path(video_id)` で取得可
- **既存テンプレ**: `services/llm.py` には既にキャプション生成系の関数があるかもしれないので確認 → なければ追加

### 入力 / 出力モデル
- 入力: アップロード済み video_id + 任意のテーマ文字列（例: 「ダイエットの食事」）
- 出力: `{instagram_caption, youtube_title, youtube_description, hashtags, cover_text_candidates}`

## Goals / Non-Goals

**Goals:**
- 動画アップロード後ワンクリックで投稿文一式を生成し、フォームに流し込めるようにする
- 既存資産（ReazonSpeech + Anthropic Claude）を最大限活用し追加コストを抑える
- カバー文字案も生成（TikTok / Edits で動画にテキスト合成する現状ワークフローを支援）
- ユーザーが結果を編集 / 再生成できる（採用しないことも自由）

**Non-Goals:**
- サムネ画像の自動生成（フレーム抽出 + 文字オーバーレイ合成）→ 将来別 change
- IG Reels `thumb_offset` の自動選択 → 将来別 change
- バズスコア再活用 / 投稿テンプレ機能 → 将来別 change
- 多言語対応（日本語のみ）
- 非同期ジョブ化（同期 60 秒前後のリクエストで十分。長くなれば将来検討）

## Decisions

### D1: ASR は ReazonSpeech（既存）
- `services/asr.py` の `transcribe_with_reazonspeech` 等を呼ぶ
- 既に動画→音声→文字起こしのフローが確立済み
- ローカル実行で追加 API コストゼロ
- 日本語に特化していて精度が高い
- 処理時間: 1 分動画で 10〜30 秒程度

### D2: LLM は既存 Anthropic Claude（`services/llm.py`）
- `LLM_PROVIDER=anthropic` で稼働中、`ANTHROPIC_API_KEY` も設定済み
- 構造化出力（JSON）に強い
- 日本語の自然な文章生成が得意
- モデル: `claude-sonnet-4-6` または同等の最新 Sonnet を使う（コスト/品質バランス）

### D3: LLM プロンプト設計

#### System
```
あなたは TikTok / Instagram Reels / YouTube Shorts 向けの SNS 運用アシスタントです。
整体院 / ヘルスケア領域のリール動画の音声書き起こしを読み、
各媒体に最適化されたキャプション・タイトル・説明文・ハッシュタグ・
カバー文字を JSON で出力してください。

スタイル指針:
- Instagram キャプション: 親近感のあるトーン、絵文字適度に、ハッシュタグは別フィールド
  に分けて本文には含めない、200 文字以内
- YouTube タイトル: クリック率を意識した訴求、70 文字以内
- YouTube 説明文: SEO を意識、結論 → 詳細 → CTA の構造、500 文字以内、最後にハッシュタグ
- ハッシュタグ: 5 個、各媒体共通で使えるもの、`#` 付き
- カバー文字案: 3 案、各 7〜12 文字以内、強い訴求、リール冒頭に表示する想定
```

#### User
```
[テーマ]（指定があれば）
{theme}

[書き起こし]
{transcript}

出力 JSON:
{
  "instagram_caption": "...",
  "youtube_title": "...",
  "youtube_description": "...",
  "hashtags": ["#xxx", ...] (5 個),
  "cover_text_candidates": ["...", "...", "..."]
}
```

### D4: 構造化出力と検証
- Anthropic Claude の structured output 機能 / tool use / "JSON モード"（プロバイダ次第）で堅牢に取得
- レスポンスを Pydantic でバリデーション、不正なら 422 で返す
- ハッシュタグは `services/hashtags.normalize_hashtags` で正規化（5 個まで、`#` 付与、重複除去）

### D5: API エンドポイント設計
- `POST /api/posts/{video_id}/suggest`
- リクエストボディ: `{theme?: string}` （任意。なくても動く）
- レスポンス: `CaptionSuggestionResponse`
- 同期処理（60 秒程度）。タイムアウト対策はフロント側で。長すぎたら将来非同期化

### D6: 失敗時のフォールバック
- ASR 失敗（音声なし・短すぎ・モデルエラー）: 422 + 「書き起こしに失敗しました」
- LLM 失敗（API エラー・JSON 不正）: 502 + 「AI 生成に失敗しました。再試行してください」
- 部分成功なし（all or nothing）

### D7: フロントエンド UX
- `/post/new` の動画プレビュー下に **「✨ AI でキャプション生成」** ボタン
- 押下 → ボタン無効化 + 「生成中…（書き起こし + AI）」表示
- 完了 → 各フォーム欄が**サジェスト値で上書き**（既存値があれば確認モーダル？ MVP は無確認上書き）
- 「カバー文字案」セクション（投稿フォーム下）に 3 案表示、コピーボタン付き
- 「再生成」ボタンで何度でも実行可

### D8: コスト管理
- LLM 1 リクエスト: 入力 ~5000 tokens + 出力 ~500 tokens
- Anthropic Sonnet 4.6 rate: 約 $0.02 / 1 リクエスト想定
- 月 30 動画 + 再生成数回 = $1〜2 / 月
- 想定外の高頻度実行を抑える機構: フロント側で重複押下抑止のみ（dev mode は問題なし）

## Risks / Trade-offs

### R1: ASR 失敗時の UX
**Mitigation**: 明確なエラーメッセージ + 手動入力フォールバック（フォームは元から手書きできるので影響軽微）

### R2: LLM 結果のばらつき
**Mitigation**: temperature=0.3 程度で安定化、「再生成」ボタンで何度でもやり直せる、最終的にユーザーが編集する前提

### R3: 処理時間（60 秒前後）の UX
**Mitigation**: ローディング状態 + 進捗表示（「書き起こし中…」「AI 生成中…」）、Cancel は要らない（短いので）

### R4: 整体院ドメインへの最適化
**Mitigation**: System prompt に「整体院 / ヘルスケア領域のリール動画」と明示。将来テーマ別 prompt も検討（別 change）

### R5: 既存編集パイプラインとの ASR 競合
**Mitigation**: 別エンドポイント・別ファイル・別 video_id ベースなので競合なし。同じ video_id で編集と並行実行する場合のみ ReazonSpeech モデルの同時利用に注意（mutex / queue は将来）

### R6: コスト膨張
**Mitigation**: 単純利用なら月 $1〜2 で済む。「再生成連打」されても 1 回 $0.02 程度なので暴走しない。Rate limit は将来検討

## Migration Plan

### Phase 1: バックエンド
1. `services/captions_ai.py` 実装
   - `transcribe_video(video_id) -> str`: 動画 → 音声 → ReazonSpeech 書き起こし
   - `generate_captions(transcript, theme=None) -> dict`: LLM 呼び出し + JSON 検証
2. `models/schemas.py` に `CaptionSuggestionRequest`, `CaptionSuggestionResponse` 追加
3. `routers/posts.py` に `POST /api/posts/{video_id}/suggest` 追加
4. テスト: ASR mock + LLM mock で 5〜8 件

### Phase 2: フロントエンド
1. `lib/api.ts` に `suggestCaptions(videoId, theme?)` 追加
2. `/post/new` ページ:
   - 「✨ AI でキャプション生成」ボタン追加（動画 upload 後表示）
   - ローディング状態 UI
   - サジェスト結果のフォーム流し込み
   - 「カバー文字案」セクション新設

### Phase 3: 検証
1. backend 全テスト pass
2. frontend tsc / eslint クリーン
3. 実機: 1 本の動画で AI 生成 → 投稿フォームに反映 → 修正 → 保存
4. commit + archive

### Rollback
- 新規エンドポイント 1 つ + UI セクション 1 つの追加なので、コミットを revert で完全に戻る
- 既存挙動（手書きフォーム）は無傷
