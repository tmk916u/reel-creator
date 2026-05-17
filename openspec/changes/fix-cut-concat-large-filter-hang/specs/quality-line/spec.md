## MODIFIED Requirements

### Requirement: 項目#14 処理時間

動画 1 本の処理時間は **10 分以内** であること (SHALL)。 hang や無限待機は MUST NOT 発生してはならない。

`cut_and_concat` 内の ffmpeg subprocess.run は **timeout=600** で fail-fast すること (SHALL)。 timeout 時は明示的に RuntimeError を raise し、 ユーザーには「処理に時間がかかりすぎました」 等のエラーメッセージが表示される。

segments が 10 個を超える場合は filter_complex を 1 つの巨大 graph にせず、 **chunk 分割 + concat demuxer** で結合すること (SHALL)。 これにより ffmpeg のメモリ消費が分散され、 docker VM resource starvation を防ぐ。

#### Scenario: timeout 発火
- **WHEN** ffmpeg cut_and_concat が 600 秒を超えても完了しない
- **THEN** RuntimeError が raise され、 ジョブは failed 状態になる

#### Scenario: 大量 segments の chunk 分割
- **WHEN** segments の数が 10 個を超える
- **THEN** segments を 10 個ずつ chunk に分割し、 各 chunk を個別 ffmpeg で処理 → concat demuxer で結合する

#### Scenario: 小規模 segments は従来通り
- **WHEN** segments ≤ 10 個
- **THEN** 1 パスの filter_complex で処理する (chunk 分割なし)

## ADDED Requirements

### Requirement: `_chunk_segments` ヘルパー

`backend/app/services/ffmpeg.py` に `_chunk_segments(segments, chunk_size=10)` を提供する (SHALL)。 segments を `chunk_size` 個ずつのリストに分割して返す。

#### Scenario: 25 segments を 10 ずつに分割
- **WHEN** `_chunk_segments(segments=25 個, chunk_size=10)`
- **THEN** 返り値は `[10 segments, 10 segments, 5 segments]` の 3 つ
