## Phase 0: LLM 単体 PoC

- [x] 0.1 `backend/scripts/director_poc.py` 作成
- [x] 0.2 既存 input.mp4 の transcript (job 2f604736 等) を読込
- [x] 0.3 LLM director に投げて clips を取得
- [x] 0.4 clips を ffmpeg で切り出して output.mp4 を生成 → 動画確認
- [x] 0.5 prompt 調整を 3-5 回イテレート
- [x] 0.6 撤退判定: 良い結果が出なければ Phase 1 中止 (フォールバック決定理由)

## Phase 1: バックエンド統合

- [x] 1.1 `app/services/director.py` 新規作成
  - `design_story(words, segments, target_duration, video_context, provider) -> list[Clip]`
  - prompt 構築 (system + user)
  - LLM 呼出 (既存 llm.py の utilities 活用)
  - JSON parser + 検証ルール (D3)
  - LLM 失敗時は空 list を返す (フォールバックトリガー)
- [x] 1.2 `app/models/schemas.py` に追加:
  - `editor_mode: Literal["rule_based", "director"] = "rule_based"`
- [x] 1.3 `app/routers/video.py` 分岐:
  - editor_mode == "director" の場合、 Stage 4 (削除候補集約) をスキップ
  - director.design_story を呼ぶ
  - 失敗時は rule_based へフォールバック (warning ログ + job.message に通知)
  - 成功時は clips の順序通り voice_segments を構成
- [x] 1.4 word boundary snap helper (D5) を director.py に実装
- [x] 1.5 字幕生成: 各 clip 内の word を抽出し words_to_segments、 clip 境界で強制 flush
- [x] 1.6 テスト (`tests/test_director.py`):
  - prompt 構築の正しさ
  - JSON 解析 + 範囲外破棄
  - フォールバック条件 (LLM error, 全 clip 破棄, 尺範囲外)
  - 順序入れ替え動作
  - word boundary snap
- [x] 1.7 docker container で全 90+ テスト pass

## Phase 2: フロントエンド UI

- [x] 2.1 編集モード選択コンポーネント追加 (ProcessingPanel か別場所)
  - ラジオボタン or トグル
  - ラベル + 説明文 + 推奨基準
  - デフォルトは「標準モード」
- [x] 2.2 API リクエスト (lib/api.ts or 該当) に `editor_mode` を含める
- [x] 2.3 director 失敗時の通知 UI (job.message を表示)
- [x] 2.4 frontend type check pass

## Phase 3: 検証 + commit

- [x] 3.1 同 input.mp4 で両モード処理して動画比較
- [x] 3.2 regression-bench.md に director 結果追加 (Y/N 評価)
- [x] 3.3 全 backend テスト pass
- [x] 3.4 frontend ビルド pass
- [x] 3.5 commit (`feat: LLM director 編集モード追加 (llm-director-editor)`)
- [x] 3.6 `openspec archive llm-director-editor`
