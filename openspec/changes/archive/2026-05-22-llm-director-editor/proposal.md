## Why

現状フロー (rule-based ボトムアップ削除) は **対症療法の積み重ね** で限界に達している。 今日 1 日で 5 commits 投入 (zombie 無音 → oversized snap → VAD-aware → clamp → 字幕 chunking) しても、 雑撮り動画 (今回の input.mp4 250s) で:

- 字幕がブツ切れ (「ダ」「お」「目標」 等の 1 文字 dialogue 残存)
- 冒頭の「結論」 が 11 秒目に登場 → リール特性 (3 秒勝負) に反する
- 「お客様が悩まれている」 が 2 回繰り返される (重複統合できていない)

これらは **意味理解レイヤーがないために構造的に解決できない問題**。 上流 (ASR 粒度、 元動画の冗長性) は変えられず、 下流 (現状フロー) で何を削るかをルールで判定するアプローチは天井に達している。

LLM director: **「いる区間を LLM が決める」 トップダウン編集** で、 上記 3 問題を構造的に解決する:
- 字幕: 意味のかたまりで設計するため、 ブツ切れが原理的に発生しない
- 冒頭: 「結論を最初に置く」 と LLM に指示できる → 順序入れ替え
- 重複: LLM が「これは同じ話」 と認識して 1 つに統合

## What Changes

新 `editor_mode` フィールドを ProcessRequest に追加し、 2 モードから選択可能にする:

- **`rule_based`** (デフォルト): 既存フロー (silence + jump_cut + coherence)
- **`director`**: 新規。 LLM に transcript 全文を渡して「残すべき区間 [start, end, role, order] のリスト」 を取得 → cut_and_concat で順序通り繋ぐ

### Backend
- `app/services/director.py` (新規): LLM director 呼出ロジック
  - `design_story(words, segments, target_duration, video_context) -> list[Clip]`
  - prompt: 「これは整体院動画の transcript。 60秒のリールにするため、 ストーリーを設計して残す区間を返せ。 hook(冒頭3秒) → reason → example → cta の構造で」
  - LLM schema: `{clips: [{start, end, role, order, text}]}` (JSON mode)
- `app/routers/video.py`: `editor_mode == "director"` の場合
  - 削除候補レイヤー (silence, jump_cut, coherence) をスキップ
  - director が指定した clips を順序通り cut_and_concat
  - LLM 失敗時 → rule_based フォールバック (warning ログ)
- `app/models/schemas.py`: `editor_mode: Literal["rule_based", "director"] = "rule_based"`

### Frontend
- 最初のステップ (動画アップロード後の設定画面) に編集モード選択 UI を追加
  - ラジオボタン or トグル
  - ラベル: 「自動編集モード」
    - 「✂️ 標準 (削るだけ)」 = rule_based
    - 「🎬 AI 監督 (ストーリー再構成)」 = director (Beta バッジ)
  - 説明ツールチップ: それぞれの特性 (削除 vs 再構成、 推奨入力タイプ)

### LLM prompt 設計 (design.md 詳細)
- System: 整体院動画ドメインを記述
- User: transcript + word timestamps + 目標尺
- Output: JSON `{clips: [...]}`、 範囲外時刻や役割不明は破棄

- BREAKING: なし (editor_mode のデフォルトは rule_based = 既存挙動)

## Capabilities

### Modified Capabilities
- `ai-jump-cut`: 新 editor_mode を追加 (ADDED Requirements: LLM director mode)

## Impact

- **Backend**:
  - `director.py` 新規 (~150 行) + prompt (~50 行)
  - `video.py` 分岐 (~30 行)
  - `schemas.py` 1 フィールド
- **Frontend**:
  - 編集モード選択コンポーネント (~50 行 TSX)
- **テスト**: 既存全件維持 + 新規 6-8 件
  - director の prompt 構造化
  - LLM 失敗時のフォールバック
  - 範囲外 clip の破棄
  - 順序入れ替え動作
- **処理時間**: director mode で +5-15 秒 (LLM 呼出 + transcript 全量送信)
- **LLM コスト**: 1 動画 +$0.05〜0.10 (transcript 5000 tokens + 出力 1000 tokens)
- **業務量産**: 雑撮り動画でも 「Y フリップ」 が出ると見込む。 regression-bench で測定
