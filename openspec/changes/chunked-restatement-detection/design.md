## Context

`backend/app/services/llm.py:detect_restatements` は word 列全体を 1 回の LLM 呼出に渡して言い直し区間を返す実装。`backend/app/routers/video.py` のジャンプカット段階で呼ばれ、結果は他検出器の出力と一緒に `merge_ranges` で統合されてから `extra_cuts` として無音区間と合成される。

実機検証（ジョブ ID `69a225c2-7d27-44d6-b4b9-5c600947c7e9`、入力 250 秒）で、LLM が言い直しの「後半数秒」しか返さず、結果として cut.mp4 に言い直し前半（約 6 秒）が丸ごと残った。同じ素材を一度カットした 74.7 秒版で同じ関数を呼び直すと言い直し全体 8.5 秒を 1 区間で完全検出できる。原因は LLM の長尺入力に対する検出粒度の劣化と判断。

## Goals / Non-Goals

**Goals:**
- 60 秒以上の入力でも言い直し検出を完全検出に近づける
- 既存呼出側（`video.py`）のコードを変更しない（戻り値の型・意味を維持）
- 60 秒未満では呼出回数・挙動とも従来と完全に同一（後方互換）

**Non-Goals:**
- 並列 LLM 呼出（順次でよい）
- `correct_transcript_segments` / `summarize_with_mishearings` のチャンク分割（別 change）
- ASR 側の長尺粒度問題への対処
- silent failure（0 件 vs LLM 失敗の区別なし）の可視化

## Decisions

### Decision 1: チャンクサイズ 90 秒 / オーバーラップ 15 秒

- 90 秒は cut.mp4 (74.7 秒) で完全検出できた実績から導出。多少の余裕を持たせて 90 秒
- 15 秒オーバーラップで「チャンク境界をまたぐ言い直し」を救う
- 250 秒入力なら 3 チャンク: `[0,90] [75,165] [150,240] [225,250]` の最大 4 チャンク

**代替案**:
- 60 秒チャンク: コンテキストが薄くなり LLM の判定が甘くなる懸念
- 120 秒チャンク: 検証済みの安全ラインを超える
- オーバーラップなし: 跨ぎを見落とす

### Decision 2: 60 秒未満は分割しない（後方互換ゲート）

word 列の総尺（`max(end) - min(start)`）が 60 秒未満なら従来どおり単一呼出。これにより:
- 短尺動画の既存挙動・LLM コストを変えない
- 既存のユニットテスト・スナップショットへの影響を最小化

### Decision 3: チャンク境界は word 境界にスナップ

- チャンクの理論境界（例: 90.0 秒）を「その時刻以降に start を持つ最初の word の start」へスナップ
- これにより word の text を途中で切らない
- 既存の `snap_silences_to_word_boundaries` は **使わない**（あれは「削除区間」を word 境界に揃える関数で、ここでの用途と異なる）
- llm.py 内部に小さなヘルパー `_split_words_into_chunks(words, chunk_sec, overlap_sec)` を持つ

### Decision 4: 結果マージは呼出側に任せる

各チャンクの結果を flat に append したリストを返す。重複（オーバーラップ範囲）は `video.py` 側の既存 `merge_ranges(... + restatement_cuts + ...)` が自然に統合する。`detect_restatements` 内では `merge_ranges` を import しない。

**代替案**:
- 関数内で merge: 依存が増える（jump_cut.py を import）。既存呼出側が merge_ranges を持っているので不要

### Decision 5: 部分成功を許容（チャンク単位のエラーハンドリング）

各チャンクの LLM 呼出は独立した try/except に包む。1 チャンクが失敗しても他のチャンクの検出結果は採用する。失敗チャンクは `logger.warning` で記録。全チャンク失敗時は従来同様に空リストを返す。

### Decision 6: ログ出力

- `logger.info("restatement chunked: chunks=%d total_ranges=%d", n_chunks, len(result))`
- 失敗チャンクは `logger.warning("chunk %d/%d failed: %s", i, n, err)`

### Decision 7: out-of-range フィルタはチャンク単位で適用

既存の `min_t / max_t` 範囲外チェックを、チャンク内の word 列の `min/max` で行う。LLM がチャンクの外を返したらドロップ。

## Risks / Trade-offs

- [LLM 呼出回数増] → 250 秒入力で 1 回 → 3〜4 回に増加。料金とレイテンシのトレードオフ。許容（リール用途の少数処理が前提）
- [チャンク境界の言い直しが見落とされる] → 15 秒オーバーラップで救う。それでも跨ぐ 15 秒超の言い直しは稀
- [部分成功で「穴」ができる] → ログには出るが metadata 化されない。将来の silent failure 可視化 change のスコープ
- [テストでの LLM モック工数] → 既存テストが detect_restatements を呼んでいれば、チャンク分割の挙動を別途モック対応が必要

## Migration Plan

1. `detect_restatements` を新実装に差し替え（同一シグネチャ）
2. 60 秒未満は従来挙動と完全一致するため、既存テストは追加修正不要を期待
3. ロールバック: 1 関数の差し戻しのみ

## Open Questions

なし（Q1–Q5 すべて決定済み）。
