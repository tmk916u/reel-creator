## MODIFIED Requirements

### Requirement: 項目#7 字幕の自然な切れ目

字幕の Dialogue は **意味のかたまり** で区切られていなければならない (SHALL)。 具体的には以下の順序で chunk 境界を決定する:

1. **強境界 (必ず flush)**: word.text 末尾が句読点 「。」「、」「!」「?」 で終わる場合、 その word 直後で flush
2. **中境界 (flush)**: 次 word との時刻 gap が **0.4 秒以上** の場合 (発話の自然な間 = 意味の区切り) で flush
3. **弱境界 (条件付き flush)**: chunk 内累積文字数が 12 文字以上 かつ 上記 1, 2 で flush されなかった場合のみ flush

word の途中で改行する (1 文字 dialogue が独立行になる) ことは **MUST NOT**。 ただし `clamp_oversized_word_ends` で `_orig_end` が設定された word (ASR ノイズで word.text と実発話が一致しない) は **独立 chunk として隔離** (SHALL)。

旧仕様の「助詞末尾抑制 (`_trailing_particles` リスト)」 ロジックは **廃止** (MUST NOT)。 word gap と句読点による境界判定で同等以上の品質を達成する。

#### Scenario: 句読点による強境界
- **WHEN** word.text 末尾が 「。」 で終わる
- **THEN** その word の直後で必ず flush し、 次 word から新 dialogue を開始する

#### Scenario: word gap による中境界
- **WHEN** 隣接する 2 word の gap (`next.start - cur.get("_orig_end", cur.end)`) が 0.4 秒以上
- **THEN** cur で flush し、 next から新 dialogue を開始する

#### Scenario: clamp 済み word の隔離
- **WHEN** word が `_orig_end` フィールドを持つ (clamp 済み)
- **THEN** その word は単独で 1 dialogue にする (前後 word と結合しない)

#### Scenario: 短 gap の連続発話は結合
- **WHEN** word gap が 0.4 秒未満で chunk 文字数が 12 文字未満
- **THEN** flush せず次 word を取り込んで chunk を延長する

### Requirement: 項目#8 字幕の読みやすい長さ

字幕の Dialogue のうち、 **2〜20 文字に収まるものが 90% 以上** (SHALL) でなければならない。

1 文字 dialogue (clamp 済み word を除く) は隣接 dialogue と統合可能 (SHALL)。 ただし統合後の合計が 20 文字を超える場合や、 前段が句点で終わっている場合は統合しない (MUST NOT)。

#### Scenario: 通常 dialogue の文字数範囲
- **WHEN** word_gap 中境界 + 句読点強境界で chunk を区切る
- **THEN** Dialogue の 90% 以上が 2〜20 文字に収まる

#### Scenario: 1 文字 dialogue の統合
- **WHEN** 1 文字 dialogue (clamp 済みでない) があり、 前後 dialogue との結合で 20 文字以下になる
- **THEN** 統合する

#### Scenario: clamp 済み 1 文字 dialogue は維持
- **WHEN** clamp 済み word (例: 「お」) で 1 文字 dialogue になっている
- **THEN** 統合せず単独 dialogue として残す (中身が壊れているため他 word との結合は誤り)

## ADDED Requirements

### Requirement: ASR ノイズの重複文字正規化

字幕生成パイプラインは word.text の連続重複文字を正規化する SHALL。 ReazonSpeech の subword 重複出力 (「ほほとんど」「ダエット」のうち重複部分など) を、 字幕表示前に去重する。

正規化規則:
- 同一文字が **2 連続** の場合は 1 文字に圧縮 (例: 「ほほとんど」 → 「ほとんど」)
- 同一文字が **3 連続以上** の場合は意図的な強調と見なして保持 (例: 「あああ」 → 「あああ」)

#### Scenario: 2 連続重複の圧縮
- **WHEN** word.text に「ほほとんど」 が含まれる
- **THEN** 字幕では「ほとんど」 として表示される

#### Scenario: 3 連続の保持
- **WHEN** word.text に「あああ」 が含まれる
- **THEN** 字幕でも「あああ」 として表示される
