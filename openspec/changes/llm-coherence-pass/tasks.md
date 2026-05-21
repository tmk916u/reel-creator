## 1. インフラ・フラグ

- [x] 1.1 環境変数 `ENABLE_LLM_COHERENCE_PASS`（default `0`）と `LLM_COHERENCE_PASS_DRY_RUN`（default `0`）を `backend/.env.example` に追記
- [x] 1.2 `backend/app/services/llm.py` に環境変数を読む helper を追加（`_coherence_enabled` / `_coherence_dry_run`）

## 2. プロンプト・スキーマ実装

- [x] 2.1 `backend/app/services/llm.py` に Pydantic モデル `_CoherenceDeletion` と `_CoherenceResponse` を追加
- [x] 2.2 プロンプト文字列を `_COHERENCE_SYSTEM_PROMPT` 定数として実装。few-shot は入れず指示文のみで記述
- [x] 2.3 入力 word 列を JSON 化する `_format_words_for_coherence(words)` を追加（既存 `_format_transcript` と分離）

## 3. detect_coherence_violations 関数実装

- [x] 3.1 `backend/app/services/llm.py` に `detect_coherence_violations(words: list[dict]) -> dict` を追加（戻り値は dict、deletions/summary/chunks_total/chunks_failed/guard_actions を含む）
- [x] 3.2 `ENABLE_LLM_COHERENCE_PASS` が OFF なら即 empty result を返す
- [x] 3.3 `LLM_PROVIDER` 未設定または API キー欠如時は warning を出して empty を返す
- [x] 3.4 総尺 60 秒未満なら単一呼出。60 秒以上なら既存 `_split_words_into_chunks` で分割し各チャンクで LLM を呼ぶ
- [x] 3.5 各チャンクの応答を Pydantic で validate。スキーマ違反は warning + スキップ
- [x] 3.6 チャンク単位の暴走ガード（削除総時間 > 30%）を実装。違反チャンクは丸ごとドロップ
- [x] 3.7 個別の削除候補が 8 秒超ならドロップ（チャンク単位ではなく削除候補単位）
- [x] 3.8 チャンク間の重複は呼出側の `merge_ranges` に任せる（関数内で merge しない）
- [x] 3.9 `logger.info("coherence pass: chunks=%d failed=%d input_words=%d deletions=%d dropped_seconds=%.2f dry_run=%s", ...)` を出力

## 4. 全体ガード（呼出側）

- [x] 4.1 残存 word 数 50% チェック: `detect_coherence_violations` の戻り値を仮適用してみて、残存 word 数が元の 50% 未満なら結果を破棄
- [x] 4.2 上記ガードは `backend/app/routers/video.py` の呼出側で実装（関数内のチャンク単位ガードでは見えない総合的な暴走を検出するため）

## 5. video.py 統合

- [x] 5.1 既存のジャンプカット検出群が `extra_cuts` を作る既存箇所（line 404-407）の**直後**に本パスを挿入
- [x] 5.2 既存 `extra_cuts` を考慮した「生存 word 列」を取り出す（word.start が cut range 内に入らない word のみ）
- [x] 5.3 `detect_coherence_violations(surviving_words)` を呼ぶ
- [x] 5.4 Dry-run モードならログ + JSON ダンプして終了。`extra_cuts` には追加しない
- [x] 5.5 本適用時は暴走ガード（残存 50% チェック）を通過したら `extra_cuts = merge_ranges(extra_cuts + coh_deletions)`
- [x] 5.6 jump_cut_notes に「コヒーレンスパス: deletions=N total=T.TTs」を追記してユーザー表示

## 6. Dry-run JSON ダンプ

- [x] 6.1 `job_dir/coherence_dryrun.json` に `{"deletions": [...], "summary": "...", "applied": false, "rejected_by_overall_guard": bool, "guard_actions": [...]}` 形式で書き出す
- [x] 6.2 guard_actions には「runaway」「dropped」「out-of-range」等のガード作動履歴を含める

## 7. テスト

- [x] 7.1 `detect_coherence_violations` が `ENABLE_LLM_COHERENCE_PASS=0` で即 empty を返すテスト
- [x] 7.2 LLM_PROVIDER 未設定で empty を返すテスト
- [x] 7.3 短尺入力で LLM が 1 回だけ呼ばれるテスト
- [x] 7.4 長尺入力でチャンク数分だけ呼ばれるテスト
- [x] 7.5 LLM が削除総時間 > 30% を返したらチャンク全体が破棄されるテスト
- [x] 7.6 LLM が 8 秒超の単一削除を返したらその候補だけドロップされるテスト
- [x] 7.7 LLM が例外を投げても empty を返し warning を出すテスト
- [x] 7.8 Pydantic スキーマ違反応答が warning + スキップになるテスト
- [ ] 7.9 video.py の統合テスト: 残存 word 50% 未満の応答を破棄し既存 `extra_cuts` のみで処理続行（dry-run評価で代替予定）
- [ ] 7.10 Dry-run モードで `extra_cuts` に追加されないことを確認するテスト（dry-run評価で代替予定）

## 8. Dry-run 評価（合格基準前段）

- [ ] 8.1 回帰ベンチ 4 本（`reel_69a225c2`, `reel_51edb5c1`, `reel_9989a632`, `reel_19e6303c`）の元素材を再アップロードしてジョブを起動
- [ ] 8.2 各ジョブを `ENABLE_LLM_COHERENCE_PASS=1 LLM_COHERENCE_PASS_DRY_RUN=1` で実行
- [ ] 8.3 `coherence_dryrun.json` を 4 本目視。明らかな誤削除（重要発話を切ろうとしている）がないか確認
- [ ] 8.4 誤削除あればプロンプトかガード値を調整して 8.2 に戻る

## 9. 本適用 + 合格判定

- [ ] 9.1 `LLM_COHERENCE_PASS_DRY_RUN=0` で 4 本を再処理
- [ ] 9.2 出力動画を盲検評価（Y/N + 却下理由）
- [ ] 9.3 **flip ≥ 2 本**（N → Y）達成なら本 change の Acceptance Criteria 合格、archive へ
- [ ] 9.4 flip < 2 なら原因分析メモを `design.md` の Open Questions に追記、フラグ OFF に戻して別 change で再挑戦

## 10. ドキュメント

- [ ] 10.1 `backend/.env.example` に `ENABLE_LLM_COHERENCE_PASS` と `LLM_COHERENCE_PASS_DRY_RUN` のコメント付き記載
- [ ] 10.2 `backend/app/services/llm.py` の `detect_coherence_violations` の docstring に挿入位置・入力・ガード戦略を記載
- [ ] 10.3 `.planning/intel/regression-bench.md` を更新し、本 change 適用後の Y/N 結果と flip 数を追記
