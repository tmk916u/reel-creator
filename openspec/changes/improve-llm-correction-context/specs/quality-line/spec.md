## MODIFIED Requirements

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊 + 重複表示)は 1 動画あたり 0〜1 個に抑えられること (SHALL)。

1 段目 ASR の認識ミスを吸収するため、 以下の **3 段防御** をすべて備えること (SHALL):

1. **動画固有辞書** (`summarize_with_mishearings`): LLM が動画 transcript 全体から誤認識ペアを抽出する。 プロンプトには「subword 化された短い断片」「意味不明な並び」「反義語的誤り」「1 字目欠落」 などの例を含むこと
2. **静的辞書** (`jp_corrections.txt`): 繰り返し観測される誤認識を蓄積
3. **LLM 校正** (`correct_transcript_segments`): 動画固有辞書で吸収しきれない subword 列を、 文脈から推測して書き換える。 長さ制約は **-70% 〜 +50%** の範囲で書き換えを許容すること (SHALL)

#### Scenario: subword 断片の動画固有辞書による吸収
- **WHEN** ASR が「事への」 「悪い要」 「ボメ」 のような subword 断片を出す
- **THEN** `summarize_with_mishearings` がこれらを誤認識として抽出し、 `apply_corrections_to_text` で正しい text に置換される

#### Scenario: LLM 校正による文脈推測修正
- **WHEN** subword 列 5 文字以下で意味が通らない segment が存在
- **THEN** `correct_transcript_segments` が周辺の文脈から推測し、 意味の通る日本語に書き換える (元の -70% 〜 +50% の範囲)

#### Scenario: 長さチェックの拒否範囲
- **WHEN** LLM が segment を 元の 2.5 倍超、 もしくは 15 文字以上長く書き換える
- **THEN** その修正は拒否され、 retry 機構 (控えめ校正) で再試行される
