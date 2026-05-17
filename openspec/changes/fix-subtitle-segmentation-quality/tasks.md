## 1. 実装

- [x] 1.1 `subtitle.py` の `_trailing_particles` を拡張: `"はがをにでとのもへやかなてばしず"` (4 文字追加)
- [x] 1.2 `words_to_segments` の句読点 flush セットから「、」 を除外: `"。！？!?."` のみで flush
- [x] 1.3 `_merge_short_segments` を強化:
  - 新引数 `min_chars=8` を追加(8 文字未満を「短すぎる」 と定義)
  - 統合判定: どちらかが min_chars 未満 + 合計 ≤ max_chars × 1.4 + 前段が句点で終わっていない
  - 既存の min_dur (< 0.6 秒) 判定はそのまま維持
- [x] 1.4 `words_to_segments` から `_merge_short_segments` 呼出時の `max_chars` を `max(max_chars * 1.4, 14)` に調整

## 2. テスト追加・修正

- [x] 2.1 既存 115 件のテストが PASS することを確認 (2 件の input にギャップを追加して意図を維持)
- [x] 2.2 `tests/test_subtitle.py` に新規テスト 5 件:
  - 「て」 末尾で flush 抑制 (接続助詞)
  - 「、」 では flush されない
  - 8 文字未満の Dialogue が統合される
  - 統合候補が max_chars × 1.4 を超えると統合されない
  - 前段が句点で終わる場合は統合しない (文の境界尊重)
- [x] 2.3 全 120/120 PASS

## 3. ベースライン再測定

- [x] 3.1 `test-videos/seitai_food.mov` を再処理(tight preset, max_chars=10) → job df58f7dc
- [x] 3.2 `measure_quality.py` 実行: #7 38.7% → 26.7%、 #8 41.9% → 50% で改善 (完全合格は未達)
- [x] 3.3 出力字幕の冒頭 5 Dialogue 目視確認: 短い断片が減り、 8-14 文字レンジに集中する傾向
- [x] 3.4 #5 #6 ✅ に退行なし、 #4 動画長 94.5s ✅、 #14 処理時間 256s ✅

## 4. baseline.md / HANDOVER.md 更新

- [x] 4.1 `.planning/HANDOVER.md` に最新ベースライン (df58f7dc) を反映
- [x] 4.2 業務量産品質ライン 9/14 (推定) で業務投入可能ラインにほぼ到達と記録
- [x] 4.3 残課題 (#7 #8 完全合格、 #10 #12 未測定) を将来の change 候補として明示

## 5. archive 準備

- [x] 5.1 全タスクの完了確認
- [x] 5.2 ベースライン再測定で #7 #8 が改善 (完全合格未達は許容、 美観の問題で業務量産には致命的でない)
- [ ] 5.3 `openspec archive fix-subtitle-segmentation-quality` で archive
