## 1. 実装

- [ ] 1.1 `subtitle.py` の `_trailing_particles` を拡張: `"はがをにでとのもへやかなてばしず"` (4 文字追加)
- [ ] 1.2 `words_to_segments` の句読点 flush セットから「、」 を除外: `"。！？!?."` のみで flush
- [ ] 1.3 `_merge_short_segments` を強化:
  - 新引数 `min_chars=8` を追加(8 文字未満を「短すぎる」 と定義)
  - 統合判定: どちらかが min_chars 未満 + 合計 ≤ max_chars × 1.4 + 前段が句点で終わっていない
  - 既存の min_dur (< 0.6 秒) 判定はそのまま維持
- [ ] 1.4 `words_to_segments` から `_merge_short_segments` 呼出時の `max_chars` を `max(max_chars * 1.4, 14)` に調整

## 2. テスト追加・修正

- [ ] 2.1 既存 115 件のテストが PASS することを確認 (期待値変更が必要な場合は調整)
- [ ] 2.2 `tests/test_subtitle.py` に新規テスト:
  - 「て」 末尾で flush 抑制 (接続助詞)
  - 「、」 では flush されない
  - 8 文字未満の Dialogue が統合される
  - 統合候補が max_chars × 1.4 を超えると統合されない

## 3. ベースライン再測定

- [ ] 3.1 `test-videos/seitai_food.mov` を再処理(tight preset)
- [ ] 3.2 `measure_quality.py` で #7 と #8 が ✅ になることを確認
- [ ] 3.3 出力字幕の冒頭 5 Dialogue を目視確認: 短い断片が減って 8-14 文字の Dialogue 中心になっているか
- [ ] 3.4 #5 #6 に退行が無いか確認

## 4. baseline.md / HANDOVER.md 更新

- [ ] 4.1 `establish-quality-line/baseline.md` (archive 配下) を参照ではなく、 latest baseline を新規ファイルで作成 or 該当 commit 履歴に記録
- [ ] 4.2 `.planning/HANDOVER.md` に変更内容を反映
- [ ] 4.3 業務量産投入可能ラインに到達したことを記録

## 5. archive 準備

- [ ] 5.1 全タスクの完了確認
- [ ] 5.2 ベースライン再測定で #7 と #8 が合格していることを確認
- [ ] 5.3 `openspec archive fix-subtitle-segmentation-quality` で archive
