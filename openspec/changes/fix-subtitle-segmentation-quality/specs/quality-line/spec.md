## MODIFIED Requirements

### Requirement: 項目#7 字幕の自然な切れ目

字幕の Dialogue のうち、 末尾が単一文字格助詞・接続助詞・活用語尾 (はがをにでとのもへやかなてばしず) で終わるものは **10% 未満** (SHALL) にしなければならない。

接続助詞 (「て」「ば」「し」「ず」 など) や 格助詞 (「は」「が」「を」「に」 など) の直後で flush するのは、 ハードリミット (`max_chars × 1.5` 以上) に達した時だけ許容される (SHALL)。 それ以外は次の語まで持ち越すこと (SHALL)。

また、 句読点「、」 では flush せず、 「。」 「！」 「？」 等の文末記号のみで flush すること (MUST)。 「、」 で切ると短い断片が量産され、 #8 文字数比率を下げる副作用がある。

#### Scenario: 助詞抑制の動作
- **WHEN** current_text が「結論から言うと一番大事なのは」 で次の word が「メンタル」
- **THEN** 「は」 直後で flush せず、 「メンタル」 まで持ち越して 「結論から言うと一番大事なのはメンタル」 1 つの Dialogue にする(hard_limit 内なら)

#### Scenario: 「、」 では flush しない
- **WHEN** current_text に「、」 が含まれる
- **THEN** 「、」 自体では flush せず、 句点 or hard_limit まで継続

### Requirement: 項目#8 字幕の読みやすい長さ

字幕の Dialogue のうち、 **8〜14 文字に収まるものが 70% 以上** (SHALL) でなければならない。

8 文字未満の Dialogue は隣接 Dialogue と統合可能(SHALL)。 ただし統合後の合計が max_chars × 1.4 を超える場合や、 隣接前段が句点で終わっている場合は統合しない (MUST NOT)。

#### Scenario: 短い Dialogue の統合
- **WHEN** 隣接する 2 つの Dialogue のうち、 どちらかが 8 文字未満で、 合計が max_chars × 1.4 以下、 前段が句点で終わっていない
- **THEN** 2 つを統合して 1 つの Dialogue にする

#### Scenario: 統合の上限保証
- **WHEN** 統合候補の合計文字数が max_chars × 1.4 を超える
- **THEN** 統合しない(独立した Dialogue として残す)
