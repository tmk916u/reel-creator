# backend/app/services/silence.py


def compute_voice_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.0,
) -> list[dict]:
    """無音区間リストから有音区間リストを算出する。

    Args:
        silences: [{"start": float, "end": float}, ...] 無音区間のリスト
        total_duration: 動画の総再生時間（秒）
        padding: 有音区間の前後に追加するパディング（秒）

    Returns:
        [{"start": float, "end": float}, ...] 有音区間のリスト
    """
    if not silences:
        return [{"start": 0.0, "end": total_duration}]

    sorted_silences = sorted(silences, key=lambda s: s["start"])

    segments = []
    current_pos = 0.0

    for silence in sorted_silences:
        seg_start = current_pos
        seg_end = silence["start"]

        if seg_end > seg_start + 0.01:
            segments.append({"start": round(seg_start, 3), "end": round(seg_end, 3)})

        current_pos = silence["end"]

    if current_pos < total_duration - 0.01:
        segments.append({"start": round(current_pos, 3), "end": round(total_duration, 3)})

    return segments
