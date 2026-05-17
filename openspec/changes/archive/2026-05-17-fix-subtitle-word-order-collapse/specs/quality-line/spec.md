## MODIFIED Requirements

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊)は 1 動画あたり 0〜1 個に抑えられること(SHALL)。 特に subword レベルの語順崩壊(例:「様が悩まれているダイエットお客」のような順序乱れ)は **MUST NOT** 発生してはならない。

字幕用 words は cut2.mp4(または施策F 未発動時は cut.mp4)を直接 transcribe したものを使うこと(SHALL)。 1段目 transcribe (元動画) の word を `_filter_words_by_segments` で 2 段 remap した結果を字幕に使うのは **MUST NOT** (過去にこの構成で語順崩壊が確認された)。

#### Scenario: 誤認識率の目視判定
- **WHEN** テスト動画の出力字幕を目視確認
- **THEN** 期待値ドキュメントの「想定される誤認識パターン」に該当しない箇所での誤認識が 1 件以下

#### Scenario: subword 語順崩壊の禁止
- **WHEN** 出力字幕の任意の Dialogue を確認
- **THEN** 「お客様」が「様...お客」のように同一語の subword が異なる位置に分散する崩壊が発生していない

#### Scenario: 字幕用 words の生成元
- **WHEN** Stage 5 の実装を確認
- **THEN** 字幕用 sub_segments は cut2.mp4 を直接 transcribe した words(3 段目)から生成されている(施策F 未発動時は cut.mp4 の 2 段目 words からのフォールバック)

### Requirement: 項目#6 字幕タイミング同期

字幕の表示時刻と音声の発話時刻のずれは 0.5 秒未満でなければならない (SHALL)。 字幕用 words は cut2.mp4 内時刻空間で生成され、 remap による時刻ねじれを発生させてはならない (MUST NOT)。

#### Scenario: 同期計測
- **WHEN** ASS の Dialogue 開始時刻と、 同じ word の word.start を比較
- **THEN** その差が 0.5 秒以内

#### Scenario: 時刻空間の一貫性
- **WHEN** 字幕用 words が生成された時刻空間を確認
- **THEN** cut2.mp4(または cut.mp4)内時刻のみで構成され、 元動画時刻からの 2 段 remap を経由していない

## ADDED Requirements

### Requirement: Stage 5b として cut2.mp4 を 3 段目 transcribe する

`_run_processing` の Stage 5 を 2 段(5a/5b)に分割し、 5b では cut2.mp4 を独立した audio として抽出した上で transcribe_with_words に流すこと (SHALL)。

#### Scenario: 3 段目 transcribe の実行
- **WHEN** 施策F が発動して cut2.mp4 が生成された
- **THEN** Stage 5b で `extract_audio(cut2_output, cut2_audio)` および `transcribe_with_words(cut2_audio, ...)` が呼ばれる

#### Scenario: 3 段目 transcribe のフォールバック
- **WHEN** 施策F が発動せず cut2.mp4 が生成されない(oversized_2nd が空)
- **THEN** Stage 5b は 3 段目 transcribe をスキップし、 2 段目の words_cut(cut.mp4 ベース)を字幕用に使う

#### Scenario: 動画カット判定との分離
- **WHEN** 動画カット判定(施策F/G) と字幕生成のロジックを確認
- **THEN** 施策F/G は 1 + 2 段目 ASR(words / words_cut)のみを使用し、 字幕生成は 3 段目 (words_cut3) のみを使用している
