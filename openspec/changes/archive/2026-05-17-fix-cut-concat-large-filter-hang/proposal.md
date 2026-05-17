## Why

業務量産品質ライン適用後、 プレビュー編集モードで動画処理が **cut_concat 55% で hang** する現象を確認 (job b8472f69)。 backend ログでは 11:34:44 で LLM 校正完了後、 **10 分間出力なし**、 CPU 0.08%、 MEM 99 MB と uvicorn worker + ffmpeg subprocess ともに idle。

原因仮説:
- `cut_and_concat` の filter_complex に 50+ trim + scale + pad + atrim + afade を 1 つの filter graph に詰め込む
- ffmpeg のメモリ消費が爆発 → docker VM レベルで resource starvation → subprocess pipe deadlock
- backend は subprocess.run の戻り待ちで blocking、 hang として観測される

業務量産で 14 本/週 を回すには hang は致命的(手動 restart が必要)。

## What Changes

- **(1) subprocess.run に timeout 追加** (fail-fast 化):
  - `cut_and_concat` の subprocess.run に `timeout=600` (10 分)
  - timeout 時は `subprocess.TimeoutExpired` を捕捉して RuntimeError に変換
  - hang → 「処理に時間がかかりすぎました」 のエラーになり、 ユーザーに通知される
- **(2) filter_complex の chunk 分割** (根治):
  - 新ヘルパー `_chunk_segments(segments, chunk_size=10)` で 10 個ずつ分割
  - chunk が 2 個以上ある場合: 各 chunk を個別 ffmpeg で trim+scale → 中間 mp4 → 最後に concat demuxer で結合
  - chunk が 1 個 (≤ 10 segments) の場合: 従来通り 1 パス filter_complex
- 既存の APIは不変 (`cut_and_concat(video, segments, output)`)
- BREAKING: なし

## Capabilities

### Modified Capabilities
- `quality-line`: 項目#14 処理時間 < 10 分 を確実に守る (hang 防止)

## Impact

- **Backend**: ffmpeg.py の `cut_and_concat` に約 50 行追加、 `_chunk_segments` 新規
- **テスト**: 既存 128 件 + 新規 3-4 件 (chunk 分割、 timeout)
- **業務量産**: hang の根絶。 大量 segments の動画でも完走
