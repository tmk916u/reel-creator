## 1. 実装

- [ ] 1.1 `asr.py` の `_transcribe_with_reazonspeech` を 2-tier retry に書き換え
- [ ] 1.2 各 transcribe 前に `model.freeze()` を try/except で呼出
- [ ] 1.3 state エラーキーワード判定 (`freeze` / `unfreeze` / `partial`) を追加
- [ ] 1.4 state エラー時に `_load_reazonspeech_model.cache_clear()` でキャッシュ破棄

## 2. テスト追加

- [ ] 2.1 既存 120 件のテストが PASS することを確認
- [ ] 2.2 `tests/test_asr.py` に新規テスト:
  - state エラー → cache_clear → 成功
  - state 以外のエラー → retry なし
  - 防御的 freeze の呼出確認

## 3. 統合確認

- [ ] 3.1 backend restart 後、 seitai_food.mov を 2 本連続処理して両方完了することを確認
- [ ] 3.2 docker logs で state エラーが出るかをモニタ、 出た場合に retry が走って成功するか確認

## 4. archive

- [ ] 4.1 全タスクの完了確認
- [ ] 4.2 `openspec archive fix-reazonspeech-model-state-leak`
