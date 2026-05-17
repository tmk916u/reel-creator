## MODIFIED Requirements

### Requirement: 項目#2 冒頭・末尾の発話保護

期待値ドキュメント `*.expected.md` の「残るべき発話キーワード」が **すべて出力字幕に出現** しなければならない。

物理保護(voice_segments に発話が含まれる)に加え、 **3段目 ReazonSpeech がその発話を認識できない場合でも、 1段目 ASR の補完によって字幕に出現する** こと。 3段目 first_word.start が動画長の 5%(最低 2 秒)を超える場合、 1段目 words を cut.mp4 / cut2.mp4 内時刻に remap した上で hybrid prepend する。

#### Scenario: 3段目 冒頭認識ミスの補完
- **WHEN** 3段目 transcribe (cut2 or cut.mp4 audio) の first_word.start が動画長 × 0.05 (最低 2 秒) を超える
- **THEN** 1段目 words を voice_segments → cut2_voices で remap し、 3段目 first_word.start - 0.1 秒より前の word を hybrid 補完として字幕用 words の先頭に prepend

#### Scenario: 3段目 冒頭認識成功時は補完しない
- **WHEN** 3段目 transcribe の first_word.start が動画長 × 0.05 (最低 2 秒) 以下
- **THEN** 1段目補完は発動せず、 字幕用 words は 3段目のみで構成される

#### Scenario: 補完 word の順序保証
- **WHEN** 1段目補完 word を字幕用に追加
- **THEN** 補完 words を start で sort してから prepend、 順序崩壊を起こさない
