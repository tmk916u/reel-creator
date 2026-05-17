## MODIFIED Requirements

### Requirement: 項目#12 トピックラベル

動画には **最低 2 件、 最大 4 件のトピックラベル** が表示されること (SHALL)。

`detect_topics` は 1 回目で 0 件を返した場合、 強制分割プロンプト (`_TOPICS_FORCE_PROMPT`) で 1 回リトライすること (SHALL)。 リトライプロンプトには「必ず最低 2 個に分割」 を明示する。

#### Scenario: 0 件のリトライ発動
- **WHEN** 1 回目の detect_topics が 0 件を返す
- **THEN** `_TOPICS_FORCE_PROMPT` で LLM をリトライし、 返り値 (2-4 件想定) を採用する

#### Scenario: 1 件以上ならリトライしない
- **WHEN** 1 回目で 1 件以上のトピックが返る
- **THEN** リトライせずそのまま採用

#### Scenario: リトライも失敗
- **WHEN** 2 回目も 0 件
- **THEN** 0 件のまま返し、 warning ログを出す
