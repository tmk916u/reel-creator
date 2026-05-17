# backend/app/services/silence.py
from app.services.jump_cut import merge_ranges


def protect_words_from_silences(
    silences: list[dict],
    words: list[dict],
    margin: float = 0.1,
) -> list[dict]:
    """silences のうち、 ASR が word を認識した範囲を穴あけして除外する。

    silero VAD や silencedetect が「無音」と判断した区間でも、 1段目 ASR が
    word を検出していれば、 それは実発話とみなして voice_segments に保護する。

    Args:
        silences: 無音区間 [{"start": float, "end": float}, ...]
        words: ASR が認識した word 列 [{"start": float, "end": float, "text": str}, ...]
        margin: word の前後に確保するバッファ(秒)。 word 直後の閉鎖音や息継ぎを軽く残す

    Returns:
        穴あけ後の silences。 word を完全に含む silence は前後 2 つに分割される。
    """
    if not words or not silences:
        return list(silences)
    out: list[dict] = []
    for s in silences:
        s_start, s_end = s["start"], s["end"]
        overlapping = [
            w for w in words
            if w["start"] < s_end and w["end"] > s_start
        ]
        if not overlapping:
            out.append(s)
            continue
        protected: list[tuple[float, float]] = []
        for w in overlapping:
            p_s = max(s_start, w["start"] - margin)
            p_e = min(s_end, w["end"] + margin)
            if p_e > p_s:
                protected.append((p_s, p_e))
        protected.sort()
        merged: list[list[float]] = []
        for p_s, p_e in protected:
            if merged and p_s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], p_e)
            else:
                merged.append([p_s, p_e])
        cursor = s_start
        for p_s, p_e in merged:
            if p_s > cursor + 0.001:
                out.append({"start": cursor, "end": p_s})
            cursor = max(cursor, p_e)
        if cursor < s_end - 0.001:
            out.append({"start": cursor, "end": s_end})
    return [r for r in out if r["end"] > r["start"]]


def compute_voice_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.04,
    extra_cuts: list[dict] | None = None,
    min_cut_length: float = 0.15,
    trim_leading: bool = False,
) -> list[dict]:
    """削除区間（無音 + 追加カット）から有音区間リストを算出する。

    Args:
        silences: 無音区間 [{"start": float, "end": float}, ...]
        total_duration: 動画の総再生時間（秒）
        padding: 有音区間の前後に残すバッファ（秒）。ぶつ切り感を軽減。
        extra_cuts: ジャンプカット由来の追加削除区間
        min_cut_length: この秒数より短い削除区間は無視（ジッタ除去）
        trim_leading: 互換のため引数は残すが、現状は **何もしない**。
          以前は最初の voice segment の start を 0 に詰めていたが、
          cut_and_concat が voice_segments を元動画時刻で切り出すため、
          start=0 にすると逆に冒頭無音を動画に含めてしまう（+ 字幕の
          時刻マッピングも壊れる）副作用があり無効化した。冒頭無音は
          VAD が検出して silences に含まれるため、compute_voice_segments
          で自動的に削除される。

    Returns:
        有音区間リスト [{"start": float, "end": float}, ...]
    """
    all_cuts: list[dict] = list(silences)
    if extra_cuts:
        all_cuts.extend(extra_cuts)

    if not all_cuts:
        return [{"start": 0.0, "end": round(total_duration, 3)}]

    merged_cuts = merge_ranges(all_cuts)
    merged_cuts = [c for c in merged_cuts if c["end"] - c["start"] >= min_cut_length]

    if not merged_cuts:
        return [{"start": 0.0, "end": round(total_duration, 3)}]

    raw_segments: list[dict] = []
    current_pos = 0.0

    for cut in merged_cuts:
        seg_start = current_pos
        seg_end = min(cut["start"], total_duration)

        if seg_end > seg_start + 0.01:
            raw_segments.append({"start": seg_start, "end": seg_end})

        current_pos = max(current_pos, cut["end"])

    if current_pos < total_duration - 0.01:
        raw_segments.append({"start": current_pos, "end": total_duration})

    if padding > 0:
        padded: list[dict] = []
        for s in raw_segments:
            padded.append({
                "start": max(0.0, s["start"] - padding),
                "end": min(total_duration, s["end"] + padding),
            })
        merged: list[dict] = []
        for s in padded:
            if merged and s["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], s["end"])
            else:
                merged.append(dict(s))
    else:
        merged = [dict(s) for s in raw_segments]

    # trim_leading は副作用のため一時無効化（docstring 参照）
    return [{"start": round(s["start"], 3), "end": round(s["end"], 3)} for s in merged]
