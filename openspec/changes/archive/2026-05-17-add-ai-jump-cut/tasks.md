## 1. 依存追加と設定

- [x] 1.1 `backend/requirements.txt` に `openai` と `anthropic` を追加（両プロバイダ対応のため）
- [x] 1.2 `backend/.env.example` に `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` を追加
- [x] 1.3 `backend/app/data/` ディレクトリを作成し、`jp_fillers.txt` に日本語フィラー辞書を保守的に投入（「えーっと」「あのー」「えー」「あの」「まあ」「なんか」「そのー」など最初は確実なものだけ）

## 2. Whisper 拡張

- [x] 2.1 `backend/app/services/subtitle.py` に `transcribe_with_words(audio_path) -> tuple[list[Word], list[Segment]]` を追加（`word_timestamps=True` で実行、word と segment 両方を返す）
- [x] 2.2 既存の `transcribe_audio` を `transcribe_with_words` を使ってリファクタ（後方互換維持）
- [x] 2.3 word リストから SRT を生成する補助関数を追加（既存セグメント単位の出力と整合）
- [x] 2.4 `backend/tests/services/test_subtitle.py` に word-level transcript 取得のテストを追加（短い音声サンプル使用）

## 3. フィラー検出

- [x] 3.1 `backend/app/services/jump_cut.py` を新規作成
- [x] 3.2 `load_fillers() -> set[str]` を実装（`jp_fillers.txt` を読み込み、見つからなければ空セット）
- [x] 3.3 `detect_filler_ranges(words: list[Word], fillers: set[str]) -> list[Range]` を実装
- [x] 3.4 `backend/tests/services/test_jump_cut.py` にフィラー検出の単体テストを追加（モック transcript で各種ケース）

## 4. 文末テンポカット

- [x] 4.1 `detect_tempo_ranges(words: list[Word], max_pause: float = 0.4, target_pause: float = 0.2) -> list[Range]` を `jump_cut.py` に実装
- [x] 4.2 句読点判定ヘルパー（単語末尾が `、。？！` のいずれかを含むか）を実装
- [x] 4.3 テンポカットの単体テストを追加（短い間は維持、長い間は短縮）

## 5. LLM 言い直し検出

- [x] 5.1 `backend/app/services/llm.py` を新規作成
- [x] 5.2 `detect_restatements(words: list[Word]) -> list[Range]` を実装（環境変数 `LLM_PROVIDER` で OpenAI/Anthropic を切替）
- [x] 5.3 LLM プロンプトを実装（transcript を JSON で渡し、`{"ranges": [...]}` を JSON モードで返させる）
- [x] 5.4 LLM 応答を Pydantic でバリデートし、transcript の時間範囲外の range は破棄する
- [x] 5.5 例外捕捉して空リストを返す degraded fallback を実装（warning ログ付き）
- [x] 5.6 LLM_PROVIDER 未設定 or API キー欠落時は即座に空リストを返す
- [x] 5.7 `backend/tests/services/test_llm.py` で LLM クライアントをモックしたテストを追加（成功・失敗・範囲外 range のケース）

## 6. 区間マージと統合

- [x] 6.1 `merge_ranges(ranges: list[Range], join_threshold: float = 0.05) -> list[Range]` を `jump_cut.py` に実装（重複と隣接区間を統合）
- [x] 6.2 `backend/app/services/silence.py` の `compute_voice_segments` を `extra_cuts: list[Range] | None = None` 引数を受けるように拡張、無音区間と extra_cuts をマージしてから差分計算する
- [x] 6.3 `compute_voice_segments` の単体テストを拡張（extra_cuts 入力のケースを追加）

## 7. パイプライン統合

- [x] 7.1 `backend/app/models/schemas.py` の `ProcessRequest` に `enable_jump_cut: bool = False` を追加
- [x] 7.2 `backend/app/routers/video.py` の `_run_processing` を改修：
  - `enable_jump_cut` が true のときに音声抽出後に `transcribe_with_words` を呼ぶ
  - filler / tempo / restatement の各検出を呼び出して削除区間を集める
  - `compute_voice_segments` に extra_cuts として渡す
  - 字幕生成も有効な場合は同じ transcript を再利用
- [x] 7.3 進捗ステージ `jump_cut`（progress 30〜50）を追加、適切な日本語メッセージを設定
- [x] 7.4 LLM の degraded fallback 発生時に `JobResult` または進捗 message に「言い直し検出をスキップしました」相当の注記を入れる

## 8. フロントエンド対応

- [x] 8.1 `frontend/lib/api.ts` の `ProcessRequest` 型に `enable_jump_cut?: boolean` を追加
- [x] 8.2 設定ステップの UI に「AIジャンプカット」トグル（チェックボックスまたはスイッチ）を追加し、ON のときに `enable_jump_cut: true` で送信
- [x] 8.3 トグル直下に補足説明（「フィラー・言い直し・長い間を自動で削減します（LLM API使用）」）を追加

## 9. 検証

- [x] 9.1 `make test` 相当（`PYTHONPATH=. pytest tests/ -v`）でバックエンドのテストが全部通ることを確認（32 passed）
- [x] 9.2 `docker compose up --build` を実行し、サンプル動画（フィラー多めの撮って出し）を `enable_jump_cut: true` で処理して結果を目視確認
- [x] 9.3 LLM_PROVIDER 未設定状態でも処理が完走することを確認（degraded mode）（test_detect_restatements_unset_provider 等で検証済み）
- [x] 9.4 `frontend` で `npm run build` がエラーなく通ることを確認（Next.js 16.1.6, 1.2秒）

## 10. ドキュメント

- [x] 10.1 `CLAUDE.md` の Architecture セクションに `jump_cut.py` と `llm.py` を追記
- [x] 10.2 `README.md` の機能紹介に AI ジャンプカットを追記
- [x] 10.3 `.env.example` の項目について README または別途設定ドキュメントに解説を追加
