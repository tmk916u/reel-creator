# backend/app/services/silence.py
from app.services.jump_cut import merge_ranges


def build_orig_to_cut2_mapping(
    voice_segments: list[dict],
    cut2_voices: list[dict] | None = None,
) -> list[dict]:
    """元時刻 → cut2 内時刻 の 1 段マッピング table を構築する。

    voice_segments と cut2_voices を合成して、 中間状態 (cut.mp4 内時刻) を
    word が経由しないようにする。 過去の 2 段 remap で発生していた
    subword 語順崩壊を **アーキテクチャ的に** 不可能にする。

    Args:
        voice_segments: 元動画から残す範囲 [{"start": float, "end": float}, ...] (元時刻)
        cut2_voices: cut.mp4 から更に残す範囲 (cut.mp4 内時刻)。 None なら施策F 未発動

    Returns:
        [{"orig_start": float, "orig_end": float, "cut2_start": float}, ...]
        word.start が [orig_start, orig_end) 内なら
        cut2_start + (word.start - orig_start) で cut2 内時刻が得られる。
    """
    mappings: list[dict] = []
    cut_offset = 0.0
    for vs in voice_segments:
        vs_dur = vs["end"] - vs["start"]
        vs_cut_start = cut_offset
        vs_cut_end = cut_offset + vs_dur
        cut_offset = vs_cut_end
        if cut2_voices is None:
            # 施策F 未発動: cut.mp4 = 最終動画
            mappings.append({
                "orig_start": vs["start"],
                "orig_end": vs["end"],
                "cut2_start": vs_cut_start,
            })
            continue
        # 施策F 発動: cut.mp4 内時刻範囲 [vs_cut_start, vs_cut_end] が cut2_voices で更に分割される
        cut2_cum = 0.0
        for cv in cut2_voices:
            cv_dur = cv["end"] - cv["start"]
            inter_start = max(vs_cut_start, cv["start"])
            inter_end = min(vs_cut_end, cv["end"])
            if inter_end > inter_start:
                orig_off_in_vs = inter_start - vs_cut_start
                mappings.append({
                    "orig_start": vs["start"] + orig_off_in_vs,
                    "orig_end": vs["start"] + (inter_end - vs_cut_start),
                    "cut2_start": cut2_cum + (inter_start - cv["start"]),
                })
            cut2_cum += cv_dur
    return mappings


def remap_words_with_mapping(
    words: list[dict], mappings: list[dict],
) -> list[dict]:
    """word を 1 段マッピングで cut2 内時刻に変換する。

    word.start が含まれる mapping を線形探索 (mapping 数は 10-50 程度なので O(n) で十分)。
    word.end が mapping 範囲を超える場合は clamp する。

    Args:
        words: 元時刻の word 列 [{"start": float, "end": float, "text": str, ...}]
        mappings: build_orig_to_cut2_mapping で得たマッピング

    Returns:
        cut2 内時刻に変換された word 列(削除区間にかかる word は省略)
    """
    if not words or not mappings:
        return []
    out: list[dict] = []
    for w in words:
        for m in mappings:
            if m["orig_start"] <= w["start"] < m["orig_end"]:
                new_start = m["cut2_start"] + (w["start"] - m["orig_start"])
                w_end_clamped = min(w["end"], m["orig_end"])
                new_end = m["cut2_start"] + (w_end_clamped - m["orig_start"])
                if new_end > new_start + 0.001:
                    new_w: dict = {
                        "start": new_start,
                        "end": new_end,
                        "text": w["text"],
                    }
                    if "is_word_start" in w:
                        new_w["is_word_start"] = w["is_word_start"]
                    out.append(new_w)
                break
    return out


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
