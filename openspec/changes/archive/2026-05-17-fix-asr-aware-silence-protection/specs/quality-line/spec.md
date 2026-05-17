## MODIFIED Requirements

### Requirement: 項目#2 冒頭・末尾の発話保護

期待値ドキュメント `*.expected.md` の「残るべき発話キーワード」が **すべて出力字幕に出現** しなければならない。 特に **動画の冒頭 30 秒以内の発話** は、 silero VAD やその他の silence 判定によって物理的に削除されてはならない。

VAD/silence 判定で「無音」とされた区間でも、 1 段目 ASR (元動画 transcribe) が **word を認識した範囲** は voice_segments に保護されること。 これにより、 ASR と VAD の判断が食い違う場合は **ASR を優先** する設計とする。

#### Scenario: 冒頭発話の物理保護
- **WHEN** 1 段目 ASR が元時刻 0-30 秒の範囲に word を 1 つ以上認識
- **THEN** 該当 word の時刻範囲が voice_segments に含まれ、 cut.mp4 / cut2.mp4 にも音声として残る

#### Scenario: ASR-aware silence 保護の実装
- **WHEN** video.py の Stage 3 で `words` が利用可能
- **THEN** voice_segments 計算前に `protect_words_from_silences(silences, words, margin=0.1)` で silences の word 範囲が穴あけされている

## ADDED Requirements

### Requirement: `protect_words_from_silences` ヘルパー

`backend/app/services/silence.py` に `protect_words_from_silences(silences, words, margin)` 関数を提供する。 silences のうち、 word が認識された範囲を穴あけして除外する。

#### Scenario: silence と word の重なり穴あけ
- **WHEN** silence `[0.0, 20.75]`、 word `{"start": 20.38, "end": 20.94}`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 20.28}]` (word.end + margin = 21.04 > silence.end 20.75 なので後ろは無し)

#### Scenario: silence の中央に word がある場合の 2 分割
- **WHEN** silence `[0.0, 30.0]`、 word `{"start": 10.0, "end": 12.0}`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 9.9}, {"start": 12.1, "end": 30.0}]`

#### Scenario: silence と重なる word が無い場合
- **WHEN** silence `[5.0, 10.0]`、 words `[]`
- **THEN** 返り値は `[{"start": 5.0, "end": 10.0}]` (変更なし)

#### Scenario: 複数 word の merge
- **WHEN** silence `[0.0, 30.0]`、 words `[{"start": 5.0, "end": 7.0}, {"start": 6.5, "end": 8.0}]`、 margin=0.1
- **THEN** 返り値は `[{"start": 0.0, "end": 4.9}, {"start": 8.1, "end": 30.0}]` (word が merge されてから穴あけ)
