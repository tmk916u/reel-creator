## Why

現状のリール生成は「無音区間の一括削除」しかできず、フィラー（「えーっと」「あの」）や言い直し・噛みがそのまま残ってしまうため、Instagram Edits や CapCut のような「テンポの良いリール」にならない。クリエイターが手動で詰める作業を肩代わりすることで、撮って投げるだけで投稿可能な完成度に近づける。

## What Changes

- 既存の `/api/process/{job_id}` パイプラインに **AIジャンプカット段階** を追加する
- 3種類の検出ロジックを実装：
  - **フィラーワード削除**: 日本語フィラー辞書（「えーっと」「あのー」「まあ」「なんか」など）と Whisper transcript の単語レベルタイムスタンプを突合して削除区間を抽出
  - **言い直し・噛み検出**: Whisper transcript（テキスト＋タイムスタンプ）を LLM に渡し、言い直し区間のタイムスタンプ範囲を JSON で返してもらう
  - **文末テンポカット**: 句読点・文末位置を検出し、設定された閾値より長い間を短縮
- すべて完全自動・プレビューUIなし。`ProcessRequest` に `enable_jump_cut: bool` を1つ追加するだけで全機能ON/OFF
- Whisper の呼び出しを **word-level timestamps 有効化** に変更（フィラー削除に必須）
- 削除区間と既存の無音区間をマージし、`compute_voice_segments` に統合して一括カット
- LLM プロバイダは OpenAI または Anthropic（環境変数で切替）。**BREAKING**: バックエンドに新規API依存と環境変数が増える

## Capabilities

### New Capabilities
- `ai-jump-cut`: Whisper transcript とフィラー辞書・LLM 判定・文末閾値を組み合わせて削除区間を算出し、無音区間とマージするケイパビリティ

### Modified Capabilities
（既存の capability spec は未作成のため、本変更で新規追加のみ）

## Impact

- **Backend (Python)**:
  - 新規: `backend/app/services/jump_cut.py`（検出ロジック本体）
  - 新規: `backend/app/services/llm.py`（言い直し検出用 LLM クライアント、OpenAI/Anthropic 切替）
  - 新規: `backend/app/data/jp_fillers.txt`（日本語フィラー辞書）
  - 変更: `backend/app/services/subtitle.py` — word-level timestamps を返すように `transcribe_audio` を拡張、または並列の関数を追加
  - 変更: `backend/app/services/silence.py` — `compute_voice_segments` に削除区間マージ機能を追加（または上位でマージ）
  - 変更: `backend/app/routers/video.py` — `_run_processing` に jump_cut ステージ追加
  - 変更: `backend/app/models/schemas.py` — `ProcessRequest.enable_jump_cut`, `ProgressEvent.stage` の値追加
  - 変更: `backend/requirements.txt` — `openai` または `anthropic` SDK 追加
  - 変更: `backend/.env.example` — `LLM_PROVIDER`, `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 追加
- **Frontend (Next.js)**:
  - 変更: 設定ステップに「AIジャンプカット」トグル1つ追加
  - 変更: `frontend/lib/api.ts` — `ProcessRequest` 型に `enable_jump_cut` 追加
- **Cost**: LLM API 課金（1分の動画で数円程度を想定）
- **Performance**: 処理時間が +5〜15秒程度伸びる見込み（Whisper word-level + LLM 呼び出し）
- **既存機能との互換性**: `enable_jump_cut: false` がデフォルトのため既存挙動は変わらない
