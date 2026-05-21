## ADDED Requirements

### Requirement: LLM コヒーレンスパス（追加レイヤー）

システムは、機能フラグ `ENABLE_LLM_COHERENCE_PASS=1` が設定されている場合、既存ジャンプカット検出群（フィラー削除・言い直し検出・文末テンポ・遠距離冗長）を経た**生存 word 列**を別の LLM 呼出に渡し、「日本語として意味が通る最小のサブセットを得るための削除候補」を取得して `extra_cuts` に追加する SHALL。

#### Scenario: フラグ OFF では呼ばれない（後方互換）

- **WHEN** 環境変数 `ENABLE_LLM_COHERENCE_PASS` が未設定または `0` の場合
- **THEN** 本パスは実行されず、既存挙動と完全に同一の処理になる

#### Scenario: フラグ ON で生存 word 列を LLM に渡す

- **WHEN** `ENABLE_LLM_COHERENCE_PASS=1` で他検出後の生存 word 列が得られた
- **THEN** 当該 word 列が LLM に渡され、`{"deletions": [{"start": float, "end": float, "reason": string, "confidence": float}], "summary": string}` の構造化応答を得る

#### Scenario: Dry-run モードでは削除を反映しない

- **WHEN** `ENABLE_LLM_COHERENCE_PASS=1` かつ `LLM_COHERENCE_PASS_DRY_RUN=1`
- **THEN** LLM は呼ばれて削除候補は取得されるが、`extra_cuts` には追加されず、削除候補は `job_dir/coherence_dryrun.json` にダンプされる

#### Scenario: 削除総時間が 30% を超えた応答は破棄

- **WHEN** LLM の `deletions` 合計時間が生存 word 列の総尺の 30% を超える
- **THEN** その応答全体を破棄して `extra_cuts` に何も追加せず、`logger.warning` で「暴走ガード作動」を記録する

#### Scenario: 連続 8 秒超の単一削除候補はドロップ

- **WHEN** `deletions` のいずれかが連続 8 秒を超える単一区間
- **THEN** その候補のみ破棄され、他の候補は採用される

#### Scenario: 残存 word 数が 50% を切る応答は破棄

- **WHEN** LLM の `deletions` を適用した結果、残存 word 数が入力 word 数の 50% 未満になる
- **THEN** その応答全体を破棄して `extra_cuts` に追加しない

#### Scenario: LLM 失敗時はフォールバック（FAILED にしない）

- **WHEN** LLM API がエラーを返す、タイムアウトする、または応答が Pydantic スキーマで validate できない
- **THEN** ジョブは失敗せず、コヒーレンスパスの結果を空として既存検出のみで処理を継続する。`logger.warning` を出力する

#### Scenario: 60 秒未満は単一呼出

- **WHEN** 生存 word 列の総尺が 60 秒未満
- **THEN** LLM は 1 回だけ呼ばれ、応答がそのまま処理される

#### Scenario: 60 秒以上は 90 秒チャンク・15 秒オーバーラップで分割

- **WHEN** 生存 word 列の総尺が 60 秒以上
- **THEN** 既存の `_split_words_into_chunks(words, chunk_sec=90.0, overlap_sec=15.0)` で分割され、各チャンクごとに LLM が呼ばれて削除候補が flat に集約される

#### Scenario: チャンク単位の暴走ガード

- **WHEN** いずれかのチャンクで削除総時間が当該チャンクの 30% を超える
- **THEN** そのチャンクの結果のみ破棄され、他チャンクの結果はそのまま採用される

#### Scenario: チャンク単位の失敗許容

- **WHEN** 複数チャンクのうち 1 つで LLM 呼出が失敗
- **THEN** 失敗チャンクは warning ログを残してスキップされ、他チャンクの結果は採用される

#### Scenario: 削除候補は `merge_ranges` 経由で統合される

- **WHEN** 本パスの削除候補と既存検出の `extra_cuts` を統合する
- **THEN** 重複・隣接区間は既存の `merge_ranges` で 1 つに統合される

#### Scenario: LLM_PROVIDER 未設定時はスキップ

- **WHEN** `ENABLE_LLM_COHERENCE_PASS=1` だが環境変数 `LLM_PROVIDER` が未設定または対応する API キーがない
- **THEN** コヒーレンスパスは skip され、`logger.warning("coherence pass disabled: LLM not configured")` を出力する。既存検出のみで処理を継続する

### Requirement: コヒーレンスパスの観測性

システムは、コヒーレンスパスの実行・スキップ・結果サマリをログで観測可能にする SHALL。

#### Scenario: 実行ログ

- **WHEN** コヒーレンスパスが実行された（dry-run / 本適用問わず）
- **THEN** `logger.info("coherence pass: chunks=N input_words=M deletions=K dropped_seconds=T.TT dry_run=BOOL")` が記録される

#### Scenario: Dry-run の JSON ダンプ

- **WHEN** Dry-run モードでコヒーレンスパスが実行された
- **THEN** `job_dir/coherence_dryrun.json` に `{deletions: [...], summary: string, applied: false}` 形式でダンプされる
