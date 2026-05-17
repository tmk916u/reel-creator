## 1. 実装

- [ ] 1.1 `video.py` に `_dedup_leading_against_third(leading, third, window=10)` ヘルパーを追加
- [ ] 1.2 `_hybrid_prepend_leading_words` の末尾で dedup を呼出して leading から重複分を削除
- [ ] 1.3 ログ: dedup された word 数を出力

## 2. テスト追加

- [ ] 2.1 既存 120 件のテストが PASS することを確認
- [ ] 2.2 `tests/test_video_router_stage5b.py` に新規テスト:
  - 「leading 末尾と third 先頭が完全重複 → dedup で削除」
  - 「leading と third に重複なし → leading 全体保持」
  - 「window=10 を超える長い重複は最長 10 word のみ削除」

## 3. ベースライン再測定

- [ ] 3.1 seitai_food.mov を再処理(eabb58b3 と同じ動画)
- [ ] 3.2 出力字幕の冒頭 5 Dialogue を目視確認: 「お客様が悩まれている」 の重複が消えていること
- [ ] 3.3 機械測定で #5 #6 #7 #8 に退行が無いこと

## 4. archive

- [ ] 4.1 全タスクの完了確認
- [ ] 4.2 `openspec archive fix-hybrid-leading-duplicate`
