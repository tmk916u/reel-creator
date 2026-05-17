## ADDED Requirements

### Requirement: ReazonSpeech の連続呼出に対する堅牢性

`_transcribe_with_reazonspeech` は、 同一プロセス内の連続呼出で発生する `freeze()/unfreeze()` 関連の状態破損エラーから自動回復しなければならない (SHALL)。

具体的には、 transcribe が `Cannot unfreeze partially` 等のキーワードを含むエラーで失敗した場合、 `_load_reazonspeech_model.cache_clear()` でキャッシュを破棄し、 fresh load して 1 回 retry すること (SHALL)。 retry も失敗したら WhisperX フォールバックへ抜けること (SHALL)。

業務量産 14 本連続処理 (= 約 42 回の transcribe 呼出) で **1 回も hang や失敗で停止してはならない** (MUST NOT)。

#### Scenario: 状態破損エラーからの自動回復
- **WHEN** `transcribe()` が「Cannot unfreeze partially without first freezing」 を含むエラーを raise
- **THEN** `_load_reazonspeech_model.cache_clear()` が呼ばれ、 fresh load 後に再度 transcribe される

#### Scenario: state エラー以外は retry しない
- **WHEN** `transcribe()` が「audio file not found」 のような state とは無関係のエラーを raise
- **THEN** retry せず WhisperX フォールバックへ即抜ける

#### Scenario: 防御的 freeze の常時呼出
- **WHEN** transcribe 前
- **THEN** `model.freeze()` を try/except で呼出し、 内部状態を正規化する(失敗時は無視)
