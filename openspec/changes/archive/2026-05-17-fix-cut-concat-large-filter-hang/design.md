## Context

### 現状の cut_and_concat
```python
def cut_and_concat(video_path, segments, output_path, ...):
    filter_complex = _build_cut_concat_filter(segments, ...)  # 50+ trim を 1 graph に
    cmd = ["ffmpeg", "-y", "-i", video_path, "-filter_complex", filter_complex, ...]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # ↑ timeout 無し、 hang すると永遠に待つ
```

### 観測される hang
- プレビュー編集モードで silero VAD 53 + micro silence 102 = ~50 voice_segments
- filter_complex に 50 trim × 2 (video + audio) + concat = **108 フィルタ**
- 1080×1920 downscale + pad + audio fade が各 chunk に
- ffmpeg がメモリ大量消費 → docker VM frozen → subprocess pipe deadlock
- backend は subprocess.run の戻り待ちで永遠に blocking

### 量産モードでは hang しない理由
- 量産モードと編集モードで voice_segments の数自体は同じはず
- ただし編集モードでは 1 段目 transcribe を 2 回経由する分メモリ消費が増えており、 docker VM 残メモリが少なく ffmpeg が OOM 寄りに

## Goals / Non-Goals

**Goals:**
- hang の根絶 (timeout 化 + chunk 分割)
- 大量 segments の動画でも完走できる
- 既存の小規模 segments 動画は処理時間悪化なし

**Non-Goals:**
- ffmpeg 自体の最適化 (libx264 preset 変更等)
- chunk 数の動的調整 (固定 chunk_size=10 で十分)
- docker メモリ制限の変更 (環境依存)

## Decisions

### D1: timeout=600 (10 分) で fail-fast
```python
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
except subprocess.TimeoutExpired as e:
    raise RuntimeError(
        f"ffmpeg cut_and_concat timed out after 600s (segments={len(segments)})"
    ) from e
```

**理由**: hang 検知。 業務量産で「永遠に待つ」 は致命的なので、 10 分超は失敗扱い。 動画 5 分なら 1-2 分で完了するのが正常。

### D2: chunk 分割の閾値
- `chunk_size = 10` (固定)
- segments ≤ 10 個: 従来通り 1 パス
- segments > 10 個: chunk 分割
- 11 ≤ segments ≤ 50 で測ると 2-5 chunks に分かれる程度

**理由**: 10 個程度の filter chain なら ffmpeg メモリ消費は小さい。 大半の動画は 5-15 segments なので影響少ない。

### D3: chunk 結合は concat demuxer
中間 mp4 を txt ファイルに列挙して `ffmpeg -f concat -i list.txt -c copy` で結合:
- 再エンコードしない (`-c copy`) ので高速
- 全 chunk が同じ codec/解像度/fps なら問題なし

### D4: 中間ファイル管理
```python
import tempfile
import shutil
with tempfile.TemporaryDirectory(prefix="cut_chunks_") as tmpdir:
    chunk_outputs = []
    for i, chunk in enumerate(chunks):
        chunk_out = os.path.join(tmpdir, f"chunk_{i:03d}.mp4")
        # 各 chunk を従来の cut_and_concat (1 パス) と同じロジックで処理
        ...
        chunk_outputs.append(chunk_out)
    # concat demuxer で結合
    list_path = os.path.join(tmpdir, "list.txt")
    with open(list_path, "w") as f:
        for p in chunk_outputs:
            f.write(f"file '{p}'\n")
    final_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", list_path, "-c", "copy", output_path]
    subprocess.run(final_cmd, ..., timeout=120)
```

### D5: chunk 内の filter_complex 構築は既存ロジック再利用
`_build_cut_concat_filter(chunk_segments, ...)` を chunk ごとに呼ぶ。 audio fade は各 chunk の先頭/末尾に適用される (今と同じ)。

**Side effect**: chunk 境界では fade in/out が 2 重にかかる (前 chunk 末尾の fade out + 次 chunk 先頭の fade in)。 これは音的にはほぼ無音区間が短く挿入されるだけで、 視聴体験には影響しない (fade 0.08 秒)。

## Risks / Trade-offs

### R1: chunk 境界の音声 fade 二重
**Mitigation**: fade 長 0.08 秒で短い、 視聴上は気にならない

### R2: chunk 数が多いと concat demuxer も時間かかる
**Mitigation**: concat demuxer は再エンコード無しで 高速 (-c copy)。 100 chunks でも数秒

### R3: 中間ファイルがディスク容量を消費
**Mitigation**: `tempfile.TemporaryDirectory` で関数終了時に自動削除

### R4: timeout が誤発火
**Mitigation**: 600 秒は十分余裕。 業務量産で 1-4 分が正常範囲、 10 分なら明確な異常

## Migration Plan

1. `_chunk_segments(segments, chunk_size)` を追加
2. `cut_and_concat` を chunk 分割ロジックに書き換え (10 segments 以下は従来通り)
3. subprocess.run に timeout 追加
4. テスト追加: chunk 分割、 timeout 動作

### Rollback
ffmpeg.py 限定の変更。 git revert で完全に戻る。
