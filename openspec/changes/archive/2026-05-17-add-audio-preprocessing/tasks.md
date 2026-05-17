## 1. 実装

- [ ] 1.1 `backend/app/services/ffmpeg.py` の `extract_audio` に `-af afftdn=nr=12:nf=-25,loudnorm=I=-16:LRA=11:TP=-1.5` を追加
- [ ] 1.2 既存テスト (`tests/test_ffmpeg.py`) の期待値を更新

## 2. ベースライン再測定

- [ ] 2.1 seitai_food.mov を再処理
- [ ] 2.2 字幕の誤認識 (「事への」 「悪い要」 等) が減少しているか目視確認
- [ ] 2.3 処理時間の overhead (+3-8 秒) 確認

## 3. archive

- [ ] 3.1 全タスクの完了確認
- [ ] 3.2 `openspec archive add-audio-preprocessing`
