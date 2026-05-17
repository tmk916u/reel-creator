## MODIFIED Requirements

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊 + 重複表示)は 1 動画あたり 0〜1 個に抑えられること (SHALL)。

**字幕用 words は 1 段目 ASR (元動画 audio を transcribe) を、 voice_segments と cut2_voices を合成した 1 段マッピング table で cut2 内時刻に変換したもの** を使うこと (SHALL)。 中間状態 (cut.mp4 内時刻) を経由する 2 段 remap は MUST NOT 使ってはならない (順序崩壊の元凶)。

3 段目 transcribe (cut2.mp4 audio) は字幕用には MUST NOT 使ってはならない (短い context での subword 断片化が観測されたため)。

#### Scenario: 字幕用 words の生成元
- **WHEN** 字幕生成 (Stage 5b) で字幕用 words を取得
- **THEN** 1 段目 ASR の words を `build_orig_to_cut2_mapping` で得たマッピングで 1 回だけ remap した結果である

#### Scenario: 2 段 remap の禁止
- **WHEN** 字幕生成のコードを確認
- **THEN** `_filter_words_by_segments(_filter_words_by_segments(words, voice_segments), cut2_voices)` のような中間状態を経由する remap が **存在しない**

### Requirement: Stage 5b として cut2.mp4 を 3 段目 transcribe する

(廃止)字幕用 words は 1 段目 ASR + 1 段 remap で生成する。 3 段目 transcribe は字幕用には不要 (MUST NOT)。

`_run_processing` の Stage 5b では:
- 1 段目 ASR の words (Stage 3 で生成) を保持
- voice_segments と cut2_voices (施策F 未発動なら None) を `build_orig_to_cut2_mapping` で合成
- 合成 mapping で 1 段目 words を cut2 内時刻に remap → 字幕用 words

#### Scenario: 3 段目 transcribe をスキップ
- **WHEN** Stage 5b に到達
- **THEN** `extract_audio(cut2_output, cut2_audio)` および `transcribe_with_words(cut2_audio, ...)` は呼ばれない

#### Scenario: 1 段マッピングでの remap
- **WHEN** 字幕用 words の生成
- **THEN** `build_orig_to_cut2_mapping` が voice_segments と cut2_voices_used で 1 回呼ばれ、 `remap_words_with_mapping` が 1 段目 words で 1 回呼ばれる

## ADDED Requirements

### Requirement: 合成マッピング `build_orig_to_cut2_mapping` ヘルパー

`backend/app/services/silence.py` に `build_orig_to_cut2_mapping(voice_segments, cut2_voices)` を提供する (SHALL)。

返り値は `[{"orig_start": float, "orig_end": float, "cut2_start": float}, ...]` で、 word.start が `[orig_start, orig_end)` の中にあれば、 `cut2_start + (word.start - orig_start)` で cut2 内時刻が得られる。

cut2_voices が None の場合は施策F 未発動 (cut.mp4 = 最終動画) として、 voice_segments を単純に cut.mp4 内時刻にマップしたテーブルを返す。

#### Scenario: 施策F 発動時の合成
- **WHEN** voice_segments と cut2_voices の両方が与えられる
- **THEN** voice_segments の各範囲と cut2_voices の交差を計算し、 元時刻 → cut2 内時刻の直接マッピングを返す

#### Scenario: 施策F 未発動時
- **WHEN** cut2_voices が None
- **THEN** voice_segments をそのまま cut.mp4 内時刻へのマップとして返す (orig_start, orig_end, cut2_start = cut_offset)

### Requirement: `remap_words_with_mapping` ヘルパー

`backend/app/services/silence.py` に `remap_words_with_mapping(words, mappings)` を提供する (SHALL)。

各 word について、 `word.start` が含まれる mapping を探し、 cut2 内時刻に変換する。 word の `end` が mapping 範囲を超える場合は clamp する。

#### Scenario: 標準的な remap
- **WHEN** word.start が mapping[i] の範囲内
- **THEN** 返り値の word は `start = mapping.cut2_start + (word.start - mapping.orig_start)` になる

#### Scenario: 削除区間にかかる word の clamp
- **WHEN** word.end が mapping[i].orig_end を超える
- **THEN** word.end は mapping.orig_end までで clamp され、 新しい end が cut2 時刻でも対応して clamp される
