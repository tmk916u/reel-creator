# ai-jump-cut Specification

## Purpose
TBD - created by archiving change add-ai-jump-cut. Update Purpose after archive.
## Requirements
### Requirement: AIジャンプカットの有効化

システムは `ProcessRequest.enable_jump_cut` フラグで AI ジャンプカット機能の有効・無効を切り替えられる SHALL。デフォルトは `false`（既存挙動を保つ）。

#### Scenario: フラグが false の場合は実行されない
- **WHEN** `enable_jump_cut: false` で `/api/process/{job_id}` が呼び出された
- **THEN** ジャンプカット関連のステージは実行されず、無音削除のみで処理が完了する

#### Scenario: フラグが true の場合は実行される
- **WHEN** `enable_jump_cut: true` で `/api/process/{job_id}` が呼び出された
- **THEN** 無音検出に加えてフィラー削除・言い直し検出・文末テンポカットが順次実行される

### Requirement: word-level transcript の生成

ジャンプカット有効時、システムは元動画の音声に対し faster-whisper を word-level timestamps 付きで実行し、各単語の `text / start / end` を含む transcript を生成する SHALL。

#### Scenario: word-level transcript の生成成功
- **WHEN** ジャンプカット有効で処理が開始された
- **THEN** Whisper が word_timestamps=True で実行され、各単語に `start` と `end` を持つ transcript が得られる

#### Scenario: 字幕生成との共有
- **WHEN** 同じジョブで字幕焼き込みも有効になっている
- **THEN** Whisper は1回しか実行されず、word-level transcript からセグメントを再構築して SRT を生成する

### Requirement: 日本語フィラー削除

システムは `backend/app/data/jp_fillers.txt` に定義された日本語フィラーワード辞書と word-level transcript を突合し、フィラーに該当する単語の `[start, end]` を削除区間として抽出する SHALL。

#### Scenario: 辞書ヒットによる削除
- **WHEN** transcript の単語テキストが辞書のいずれかに一致する
- **THEN** その単語の `start` と `end` が削除区間リストに追加される

#### Scenario: 辞書ファイルが存在しない場合
- **WHEN** `jp_fillers.txt` が見つからない
- **THEN** フィラー削除はスキップされ、処理は他の検出だけで継続する

### Requirement: 言い直し・噛みの LLM 検出

システムは word-level transcript を LLM に渡し、JSON モードで言い直し・噛み区間のタイムスタンプを取得し、削除区間として採用する SHALL。LLM プロバイダは環境変数 `LLM_PROVIDER` で `openai` または `anthropic` を指定する。

#### Scenario: LLM 呼び出し成功
- **WHEN** LLM_PROVIDER が設定され API キーが有効
- **THEN** LLM が `{"ranges": [{"start": float, "end": float, "reason": string}, ...]}` を返し、各 range が削除区間リストに追加される

#### Scenario: LLM が transcript 範囲外のタイムスタンプを返した
- **WHEN** LLM の応答に transcript の最小〜最大時刻を外れる range が含まれている
- **THEN** その range は破棄され、有効な range のみ採用される

#### Scenario: LLM 呼び出しが失敗した場合は degraded mode
- **WHEN** LLM API がエラーを返す、またはタイムアウトする
- **THEN** ジョブは失敗せず、言い直し検出のみスキップしてフィラー削除と文末カットで処理を継続する。ログに warning を出力する

#### Scenario: LLM_PROVIDER が未設定
- **WHEN** 環境変数 `LLM_PROVIDER` が設定されていない、または対応する API キーがない
- **THEN** 言い直し検出はスキップし、フィラー削除と文末カットだけで処理を継続する

### Requirement: 文末テンポカット

システムは word-level transcript 内で句読点（`、。？！`）を含む単語の直後に `tempo_max_pause` 秒（デフォルト 0.4 秒）を超える間がある場合、その間を `tempo_target_pause` 秒（デフォルト 0.2 秒）に短縮するための削除区間を作る SHALL。

#### Scenario: 長い間が短縮される
- **WHEN** 文末単語の `end` と次単語の `start` の差が 0.4 秒を超える
- **THEN** その差分のうち 0.2 秒を残し、残りが削除区間として追加される

#### Scenario: 短い間は維持される
- **WHEN** 文末単語の後の間が 0.4 秒以下
- **THEN** 削除区間は追加されず、自然な間が保たれる

### Requirement: 削除区間のマージと有音区間算出

システムは無音検出・フィラー削除・言い直し検出・文末カットで得られた削除区間をすべてマージし（重複・隣接区間を統合）、元動画の総時間との差分から有音区間リストを算出する SHALL。

#### Scenario: 区間が重複している場合のマージ
- **WHEN** 異なる検出で時間的に重複する削除区間が複数得られた
- **THEN** 重複部分は1つに統合され、合計削除時間が二重カウントされない

#### Scenario: 隣接区間の統合
- **WHEN** 削除区間 A の終端と削除区間 B の始端の差が 50ms 未満
- **THEN** A と B は1つの区間に統合される

#### Scenario: 既存パイプラインとの互換
- **WHEN** マージ後の有音区間リストが既存の `cut_and_concat` に渡される
- **THEN** ffmpeg が現行と同じインタフェースでカット・結合を実行する

### Requirement: 進捗イベントへのステージ追加

システムは SSE 進捗ストリーム (`/api/progress/{job_id}`) でジャンプカット処理中のステージを `jump_cut` として通知する SHALL。

#### Scenario: ジャンプカット中のステージ通知
- **WHEN** ジャンプカット検出が実行中
- **THEN** `ProgressEvent.stage` が `jump_cut`、`progress` が 30〜50 の範囲、`message` が「AIで不要な間を検出中...」相当のメッセージを含む

### Requirement: 環境変数による設定

システムは以下の環境変数で AI ジャンプカットの LLM 接続を構成する SHALL：
- `LLM_PROVIDER`: `openai` または `anthropic`
- `OPENAI_API_KEY`: provider が openai のとき必須
- `ANTHROPIC_API_KEY`: provider が anthropic のとき必須

#### Scenario: provider に応じた SDK 選択
- **WHEN** `LLM_PROVIDER=openai` で言い直し検出が呼ばれる
- **THEN** OpenAI SDK が `OPENAI_API_KEY` を使って呼び出される

#### Scenario: 異なる provider への切替
- **WHEN** `LLM_PROVIDER=anthropic` に変更されて再起動された
- **THEN** Anthropic SDK が `ANTHROPIC_API_KEY` を使って呼び出される

### Requirement: 編集モードの選択

システムは `ProcessRequest.editor_mode` フィールドで 2 つの編集モードを切替えられる SHALL。

- `rule_based` (デフォルト): silence + jump_cut + coherence の削除候補をまとめて時系列順に動画を切り貼り (既存挙動)
- `director`: LLM がストーリーを設計して残すべき区間を返し、 順序通り切り貼り (新規)

#### Scenario: rule_based がデフォルト
- **WHEN** `editor_mode` を指定せずに `/api/process/{job_id}` が呼び出された
- **THEN** rule_based モードで処理され、 既存の削除候補レイヤーが動作する

#### Scenario: director モード選択
- **WHEN** `editor_mode: "director"` で `/api/process/{job_id}` が呼び出された
- **THEN** director サービス (`app/services/director.py`) が呼ばれ、 LLM が clips リストを返す

### Requirement: LLM director サービス

システムは LLM に transcript + 動画文脈を渡して、 残すべき区間 (clips) を JSON で取得する SHALL。

clips の形式:
- `start: float` - transcript 内の開始時刻
- `end: float` - transcript 内の終了時刻 (start < end)
- `role: "hook"|"reason"|"example"|"cta"` - リール構造内の役割
- `order: int` - 動画内で表示する順序 (1-indexed, 連番)
- `text: str` - 該当区間の発話 (参考、 表示には使わない)

#### Scenario: LLM 呼出成功
- **WHEN** director モードで処理開始、 LLM_PROVIDER が設定されていて API キーが有効
- **THEN** LLM が clips リストを返し、 検証ルールを通過した clips で動画が組み立てられる

#### Scenario: 不正 clip の破棄
- **WHEN** LLM が返した clip が transcript の時刻範囲外 (start < 0 or end > duration)、 または start >= end
- **THEN** その clip は破棄され、 warning ログに記録される

#### Scenario: 全 clip 破棄時のフォールバック
- **WHEN** 検証後に有効な clip が 0 個になった
- **THEN** director モードを中止し、 rule_based パイプラインに切替えて処理を継続する。 job.message に「AI 監督モード失敗のため標準モードで処理」 を記録

#### Scenario: 合計尺の妥当性チェック
- **WHEN** 有効な clips の合計尺 (Σ (end - start)) が 30 秒未満 or 90 秒超
- **THEN** director モードを中止し、 rule_based にフォールバックする (極端な短尺・長尺の動画はリールに不適)

#### Scenario: LLM API エラー時のフォールバック
- **WHEN** LLM API がエラーを返す、 タイムアウトする、 または JSON 解析に失敗する
- **THEN** director モードを中止し、 rule_based にフォールバック。 ログに error を出力

### Requirement: director モードの word boundary snap

director が指定する clip の [start, end] は文意ベースで word 境界とは限らないため、 切り出し時に word の境界に snap する SHALL。

- `snapped_start = max((w.start for w in words if w.start <= clip.start), default=clip.start)`
- `snapped_end = min((w.end for w in words if w.end >= clip.end), default=clip.end)`

これにより word の途中で動画が切れて音声が途切れる現象を防ぐ。

#### Scenario: word 境界への snap
- **WHEN** LLM が clip {start: 33.20, end: 65.45} を返したが、 該当時刻に word の境界がない
- **THEN** snap 後 {start: 33.06, end: 65.50} (最も近い word 境界) で切り出される

### Requirement: director モードの字幕生成

director モードでは、 各 clip 内の word を抽出して字幕を生成する SHALL。 clip 境界では字幕を強制 flush する (clip 跨ぎの字幕結合を禁止)。

#### Scenario: clip 境界での字幕 flush
- **WHEN** clip 1 の word 末尾と clip 2 の word 先頭が時刻的に近い (gap < 0.4 秒)
- **THEN** clip 境界で字幕は必ず flush され、 別 Dialogue として表示される

