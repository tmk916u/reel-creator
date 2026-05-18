## 1. ヘルパー実装

- [x] 1.1 `backend/app/services/llm.py` に `_split_words_into_chunks(words, chunk_sec=90.0, overlap_sec=15.0) -> list[list[dict]]` を追加。word の `start/end` を見てチャンク境界を word の `start` にスナップする。総尺 60 秒未満なら `[words]` をそのまま返す
- [x] 1.2 ヘルパー単体テストを `backend/tests/` に追加（短尺で 1 チャンク、長尺で複数チャンク、境界スナップが word の途中で切らないこと、オーバーラップ範囲の word が両方のチャンクに含まれることを検証）

## 2. detect_restatements のチャンク対応

- [x] 2.1 `detect_restatements(words)` を、`_split_words_into_chunks` で分割 → 各チャンクで `_format_transcript` + `_call_openai/anthropic` + `_extract_json` + `_RangesResponse.model_validate` を呼ぶ実装に差し替える
- [x] 2.2 各チャンク内で既存の out-of-range フィルタ（`min_t / max_t`）を、チャンク内 word 列の `min(start) / max(end)` に対して適用
- [x] 2.3 1 チャンクの例外は `logger.warning("restatement chunk %d/%d failed: %s", i, n, e)` で記録してスキップ。他チャンクの結果は維持
- [x] 2.4 全チャンク成功・失敗のサマリを `logger.info("restatement chunked: chunks=%d total_ranges=%d", n_chunks, len(result))` で記録
- [x] 2.5 戻り値は重複を含む flat な `list[dict]`（呼出側の `merge_ranges` で統合される前提）

## 3. テスト

- [x] 3.1 `detect_restatements` の既存テストが 60 秒未満の入力で従来通り 1 回しか LLM を呼ばないことを確認（LLM 呼出関数をモックして call count を assert）
- [x] 3.2 60 秒以上の入力でチャンク数分だけ LLM が呼ばれることをテスト（例: 250 秒入力で 3〜4 回）
- [x] 3.3 1 チャンクが例外を投げても、他チャンクの結果が返ることをテスト
- [x] 3.4 全チャンクが例外を投げた場合に `[]` を返すことをテスト
- [x] 3.5 オーバーラップ範囲の重複検出が呼出側でマージされることを `merge_ranges` と組み合わせて統合テスト

## 4. 動作確認

- [x] 4.1 検証ジョブ ID `69a225c2-7d27-44d6-b4b9-5c600947c7e9` の `input.mp4` （250 秒）でジョブを再実行し、cut.mp4 に冒頭の「お客様が悩まれているダイエット」言い直し前半が残らないことを確認（関数レベル検証: 冒頭の言い直し検出が 29.02-32.06 (3秒) → 28.86-46.70 (18秒) に拡大、2 回目の発話を完全カバー）
- [x] 4.2 短尺サンプル（60 秒未満）で挙動と LLM 呼出回数が従来と同一であることを確認（test_detect_restatements_short_calls_llm_once + 既存 13 テストすべて pass）

## 5. ドキュメント

- [x] 5.1 `backend/app/services/llm.py` の `detect_restatements` の docstring に「60 秒以上はチャンク分割で呼ぶ」旨を追記（1 行）
