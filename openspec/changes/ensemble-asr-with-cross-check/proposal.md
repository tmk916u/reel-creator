## Why

過去 15 件の change を投下しても、 ASR の本質的な認識ミス (「悪い要」「ボディ康」「事への」「こ律」 等) が **毎回違うパターン** で出続けている。 これは 1 つの ASR モデル (ReazonSpeech) の確率的揺らぎが原因で、 個別 fix では解決しない **構造的問題**。

業務量産で「字幕の細部を信頼できる」 状態に到達するため、 **複数 ASR の ensemble + LLM cross-check** で誤認識を構造的に削減する。

## What Changes

字幕用 1 段目 transcribe を **ReazonSpeech 単独** から **ReazonSpeech + WhisperX の ensemble** に切替:

- **Phase 1 並列実行** (asr.py 拡張):
  - `transcribe_ensemble(audio_path, initial_prompt)` を新規追加
  - ThreadPoolExecutor で ReazonSpeech と WhisperX を並列実行
  - 両方の transcript を保存 (`transcript_r.json` + `transcript_w.json` で監査用)

- **Phase 2 word 単位 cross-check merge**:
  - 時刻で aligning して word クラスタリング (start/end の overlap 50%以上で同じクラスタ)
  - **多数決ルール**:
    - 両方が同じ text → 採用 (confidence 高)
    - 片方しか認識していない → 採用 (補完)
    - 違う text → WhisperX 優先 (word 単位の安定性) かつ LLM cross-check 候補に記録

- **Phase 3 LLM cross-check**:
  - 不一致箇所 (R/W で text 異なる) のリストを context 付きで LLM に渡し、 文脈最良 text を選ばせる
  - 「ReazonSpeech 候補: X、 WhisperX 候補: Y、 前後の context: ...、 正しい text を返せ」 という prompt
  - 既存の `correct_transcript_segments` とは別の専用関数 `cross_check_disagreements`

- **video.py 統合**:
  - 1 段目 transcribe を `transcribe_ensemble` に置換
  - 字幕用 words はこの merge 結果を使う

- BREAKING: なし(内部実装の変更、 API 不変)

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#5 字幕の誤認識の少なさ を構造的に改善

## Impact

- **Backend**:
  - asr.py に `transcribe_ensemble` + ensemble merge ヘルパー (~150 行)
  - llm.py に `cross_check_disagreements` (~50 行)
  - video.py の Stage 3 で transcribe_ensemble を呼び出し
- **テスト**: 既存 134 件 + 新規 6-8 件 (ensemble merge ルール、 cross-check)
- **処理時間**: ReazonSpeech (~70秒) + WhisperX (~80秒) を並列で max(70,80) = ~80秒。 直列なら +80秒。 並列で +10秒程度のオーバーヘッド
- **コスト**: 不一致箇所のみ LLM 追加呼出。 動画 1 本あたり数件 (+$0.01)
- **業務量産**: 「悪い要」「ボディ康」 等の subword 断片化が 60-80% 削減見込み
