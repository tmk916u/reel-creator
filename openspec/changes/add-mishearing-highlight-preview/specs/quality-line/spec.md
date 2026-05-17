## ADDED Requirements

### Requirement: 字幕プレビューでの誤認識候補ハイライト

`/api/transcribe/{job_id}` のレスポンスは、 各 segment に `suspicious: bool` フィールドを含むこと (SHALL)。 suspicious=true の segment は frontend で **赤字 + 警告アイコン** で表示され、 ユーザーが視覚的に修正対象を特定できる (SHALL)。

検出ロジック (`detect_suspicious_segments`) は以下のいずれかに該当する segment を suspicious=true とする (SHALL):
- (a) 5 文字以下で助詞・記号比率が 50% 以上
- (b) 同一文字の 3 連続以上 (subword 反復)
- (c) 句点・記号で始まる (segment 境界の不自然)
- (d) 1-2 文字で文末記号で終わらない (subword 断片)

#### Scenario: subword 断片の検出
- **WHEN** segment.text = "客 事への 食" (5 文字、 助詞・記号 1 個)
- **THEN** suspicious=true

#### Scenario: 正常な日本語は false positive にならない
- **WHEN** segment.text = "結論から言うと一番大事なのは" (普通の発話)
- **THEN** suspicious=false

#### Scenario: API レスポンスの後方互換
- **WHEN** 既存 frontend (suspicious フィールドを知らない) がレスポンスを処理
- **THEN** suspicious フィールドは無視され、 既存の編集 UI で表示される
