## MODIFIED Requirements

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊 + **重複表示**)は 1 動画あたり 0〜1 個に抑えられること (SHALL)。

特に **同じテキスト sequence が連続する 2 つの Dialogue で繰り返し表示される** ことは MUST NOT 発生してはならない。 これは hybrid 補完で 1 段目 ASR と 3 段目 ASR が同じ発話を認識した結果として発生する。

hybrid 補完を発動する際、 leading words の末尾と 3 段目 words の先頭の text を比較し、 連続する subsequence が一致するなら leading から重複分を削除して prepend すること (SHALL)。

#### Scenario: 完全重複 sequence の dedup
- **WHEN** leading の末尾 7 word のテキストが 3 段目の先頭 7 word と完全一致
- **THEN** leading から末尾 7 word を削除してから prepend、 結果として字幕に重複が出ない

#### Scenario: 重複なしのケースは leading 全体を保持
- **WHEN** leading と 3 段目の先頭で text の subsequence 一致が無い
- **THEN** leading 全体が prepend される
