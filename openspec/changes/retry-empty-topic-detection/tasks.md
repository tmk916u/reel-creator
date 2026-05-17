## 1. 実装

- [ ] 1.1 `llm.py` に `_TOPICS_FORCE_PROMPT` を追加 (強制分割プロンプト)
- [ ] 1.2 `detect_topics` にリトライロジック: 1 回目 0 件 → `_TOPICS_FORCE_PROMPT` で 1 回リトライ
- [ ] 1.3 リトライ後も 0 件なら warning ログ

## 2. テスト

- [ ] 2.1 既存 132 件 PASS 確認
- [ ] 2.2 「1 回目空 → リトライで 2 件返す」 モックテスト
- [ ] 2.3 「1 回目 2 件 → リトライしない」 モックテスト

## 3. 動作確認

- [ ] 3.1 seitai_food.mov を再処理 → トピックラベル 2-4 件揃っているか確認

## 4. archive

- [ ] 4.1 全タスク完了確認
- [ ] 4.2 `openspec archive retry-empty-topic-detection`
