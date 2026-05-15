# backend/app/services/silence.py
from app.services.jump_cut import merge_ranges


def compute_voice_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.04,
    extra_cuts: list[dict] | None = None,
    min_cut_length: float = 0.15,
) -> list[dict]:
    """削除区間（無音 + 追加カット）から有音区間リストを算出する。

    Args:
        silences: 無音区間 [{"start": float, "end": float}, ...]
        total_duration: 動画の総再生時間（秒）
        padding: 有音区間の前後に残すバッファ（秒）。ぶつ切り感を軽減。
        extra_cuts: ジャンプカット由来の追加削除区間
        min_cut_length: この秒数より短い削除区間は無視（ジッタ除去）

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

    if padding <= 0:
        return [{"start": round(s["start"], 3), "end": round(s["end"], 3)} for s in raw_segments]

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

    return [{"start": round(s["start"], 3), "end": round(s["end"], 3)} for s in merged]
