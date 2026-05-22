## ADDED Requirements

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
