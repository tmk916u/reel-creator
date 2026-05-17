## Phase 1: 並列実行

- [ ] 1.1 `asr.py` に `transcribe_ensemble(audio_path, initial_prompt, model_size)` を追加
- [ ] 1.2 ThreadPoolExecutor で ReazonSpeech と WhisperX を並列実行
- [ ] 1.3 timeout=600 で fail-fast、 片方失敗時はもう片方を採用
- [ ] 1.4 両方の生 transcript を debug 用に返す

## Phase 2: word merge

- [ ] 2.1 `_ensemble_merge(r_words, w_words)` を追加
- [ ] 2.2 時刻 overlap で word クラスタリング (50% 以上を同じクラスタ)
- [ ] 2.3 多数決ルール:
  - 一致 → WhisperX 採用、 `source="agree"`
  - 不一致 → WhisperX 採用、 `source="disagreement"` + `rs_text`/`wx_text` 記録
  - WhisperX なし → ReazonSpeech 採用、 `source="rs_only"`
  - ReazonSpeech なし → WhisperX 採用、 `source="wx_only"`
- [ ] 2.4 テキスト正規化 (全角空白除去、 記号除去) 後に比較
- [ ] 2.5 テスト追加 (4 件): 完全一致 / 不一致 / 片方のみ / 部分 overlap

## Phase 3: LLM cross-check

- [ ] 3.1 `llm.py` に `cross_check_disagreements(disagreements, video_context)` を追加
- [ ] 3.2 disagreement の context (前後 N 個の word.text) を含めて LLM に渡す
- [ ] 3.3 LLM 失敗時は WhisperX 優先で fallback (= 現 merge 結果)
- [ ] 3.4 テスト追加 (2 件): LLM が正解を返す / LLM 失敗時 fallback

## Phase 4: 統合 + 検証

- [ ] 4.1 video.py の Stage 3 で `transcribe_with_words` → `transcribe_ensemble` に置換
- [ ] 4.2 既存 134 件 PASS 確認
- [ ] 4.3 seitai_food.mov 再処理 → 誤認識 (「悪い要」 等) 減少を確認
- [ ] 4.4 処理時間 < 10 分を確認

## 5. archive

- [ ] 5.1 全タスク完了確認
- [ ] 5.2 `openspec archive ensemble-asr-with-cross-check`
