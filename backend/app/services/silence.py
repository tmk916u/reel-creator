# backend/app/services/silence.py
from app.services.jump_cut import merge_ranges


def compute_voice_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.0,
    extra_cuts: list[dict] | None = None,
) -> list[dict]:
    """削除区間（無音 + 追加カット）から有音区間リストを算出する。

    Args:
        silences: 無音区間 [{"start": float, "end": float}, ...]
        total_duration: 動画の総再生時間（秒）
        padding: 互換用パラメータ（未使用）
        extra_cuts: ジャンプカット由来の追加削除区間

    Returns:
        有音区間リスト [{"start": float, "end": float}, ...]
    """
    all_cuts: list[dict] = list(silences)
    if extra_cuts:
        all_cuts.extend(extra_cuts)

    if not all_cuts:
        return [{"start": 0.0, "end": round(total_duration, 3)}]

    merged_cuts = merge_ranges(all_cuts)

    segments: list[dict] = []
    current_pos = 0.0

    for cut in merged_cuts:
        seg_start = current_pos
        seg_end = min(cut["start"], total_duration)

        if seg_end > seg_start + 0.01:
            segments.append({"start": round(seg_start, 3), "end": round(seg_end, 3)})

        current_pos = max(current_pos, cut["end"])

    if current_pos < total_duration - 0.01:
        segments.append({"start": round(current_pos, 3), "end": round(total_duration, 3)})

    return segments
