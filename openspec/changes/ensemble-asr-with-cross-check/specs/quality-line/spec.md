## MODIFIED Requirements

### Requirement: 項目#5 字幕の誤認識の少なさ

出力字幕の誤認識(誤認識 + 語順崩壊 + 重複表示)は 1 動画あたり 0〜1 個に抑えられること (SHALL)。

1 段目 transcribe は **ReazonSpeech と WhisperX の ensemble** を使うこと (SHALL)。 並列実行で両方の word を取得し、 時刻 overlap で merge する。 word 単位の不一致は LLM cross-check で文脈推測修正する (SHALL)。

#### Scenario: ensemble の並列実行
- **WHEN** Stage 3 の transcribe を実行
- **THEN** ReazonSpeech と WhisperX が ThreadPoolExecutor で並列実行され、 両方の transcript が job_dir に保存される

#### Scenario: word merge ルール
- **WHEN** WhisperX word と対応する ReazonSpeech subword クラスタの text が同じ
- **THEN** WhisperX word を採用、 source="agree"

#### Scenario: 不一致箇所の LLM cross-check
- **WHEN** WhisperX word と ReazonSpeech subword クラスタの text が異なる
- **THEN** disagreement として記録、 LLM cross-check で文脈最良 text を選ぶ

#### Scenario: 補完 (片方のみ認識)
- **WHEN** ReazonSpeech が認識した範囲を WhisperX が認識していない (silence と判断)
- **THEN** ReazonSpeech subwords を補完として ensemble words に含める

## ADDED Requirements

### Requirement: `transcribe_ensemble` 関数

`backend/app/services/asr.py` に `transcribe_ensemble(audio_path, initial_prompt, model_size)` を提供する (SHALL)。 ReazonSpeech と WhisperX を並列実行し、 merge 後の words を返す。

#### Scenario: 並列実行と merge
- **WHEN** `transcribe_ensemble(audio_path)` を呼出
- **THEN** ReazonSpeech と WhisperX が並列実行され、 merged words が返る

#### Scenario: 片方のバックエンド失敗時
- **WHEN** WhisperX が例外で失敗
- **THEN** ReazonSpeech 単独の結果を返す (フォールバック)

### Requirement: `cross_check_disagreements` 関数

`backend/app/services/llm.py` に `cross_check_disagreements(disagreements, video_context)` を提供する (SHALL)。 ensemble merge で発生した不一致箇所を LLM に渡し、 文脈最良 text を選ばせる。

#### Scenario: 不一致の LLM 解決
- **WHEN** disagreements が空でない
- **THEN** LLM が前後 context を読み、 各不一致箇所に対し正しい text を返す

#### Scenario: LLM 失敗時の fallback
- **WHEN** LLM 呼出が失敗
- **THEN** 不一致箇所は WhisperX 優先で採用 (現状の merge 結果)
