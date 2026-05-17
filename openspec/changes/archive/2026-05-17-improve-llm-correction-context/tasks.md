## 1. プロンプト強化 (llm.py)

- [ ] 1.1 `_SUMMARIZE_AND_MISHEAR_PROMPT` に subword 断片・反義語誤り・1 字目欠落の例を追加
- [ ] 1.2 抽出上限を 10 → 15 個に変更 (プロンプトと code の double check)
- [ ] 1.3 `_CORRECTION_SYSTEM_PROMPT` の長さ制約を「-50% 〜 +30%」 → 「-70% 〜 +50%」 に変更
- [ ] 1.4 `_CORRECTION_SYSTEM_PROMPT` に「短い subword 列を周辺の文脈から推測して書き換え可」 を明示

## 2. 実装側の長さチェック緩和

- [ ] 2.1 `correct_transcript_segments` 内の `len(new_text) > max(int(len(original) * 2.0), len(original) + 10)` を `> max(int(len(original) * 2.5), len(original) + 15)` に変更

## 3. テスト確認

- [ ] 3.1 既存 124 件のテストが PASS することを確認
- [ ] 3.2 test_llm.py の期待値変更が必要な箇所を更新

## 4. ベースライン再測定

- [ ] 4.1 seitai_food.mov を再処理
- [ ] 4.2 出力字幕で「事への」 「悪い要」 「ボメ」 等の誤認識が改善されているか目視確認
- [ ] 4.3 機械測定で退行なし確認

## 5. archive

- [ ] 5.1 全タスクの完了確認
- [ ] 5.2 `openspec archive improve-llm-correction-context`
