# backend/app/services/subtitle.py
from pathlib import Path


_SUSPICIOUS_BREAK = set("、ー　 ")  # 区切り記号(空白・読点・長音)
_SUSPICIOUS_END = set("。!?")        # 文末記号


def detect_suspicious_segments(segments: list[dict]) -> list[bool]:
    """各 segment が誤認識候補かを判定する。 True なら frontend で赤字ハイライト。

    検出ヒューリスティック (いずれかに該当で suspicious):
    (a) text に区切り記号 (空白・読点・長音) を含み、 かつ全長 8 文字以下
        (subword 断片化で「客 事への 食」 のようになる)
    (b) 同一文字の 3 連続以上 (ASR 反復ミス、「ああある」 等)
    (c) 句点・記号で始まる (segment 境界の不自然)
    (d) 1-2 文字で文末記号で終わらない (孤立 subword 断片)

    Returns: 各 segment に対する bool のリスト
    """
    result: list[bool] = []
    for s in segments:
        text = (s.get("text") or "").strip()
        susp = False
        if not text:
            result.append(False)
            continue

        # (a) 区切り記号を含む 8 文字以下 (subword 断片)
        if len(text) <= 8 and any(c in _SUSPICIOUS_BREAK for c in text):
            susp = True

        # (b) 同一文字の 3 連続
        if not susp:
            for i in range(len(text) - 2):
                if text[i] == text[i + 1] == text[i + 2]:
                    susp = True
                    break

        # (c) 句点・記号で始まる
        if not susp and text[0] in "、。!?,.":
            susp = True

        # (d) 1-2 文字で文末記号でない
        if not susp and 1 <= len(text) <= 2 and text[-1] not in _SUSPICIOUS_END:
            susp = True

        result.append(susp)
    return result


def _format_timestamp(seconds: float) -> str:
    """秒数をSRTタイムスタンプ形式に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    """Whisperのセグメントリストをsrt形式の文字列に変換"""
    if not segments:
        return ""

    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    return "\n".join(lines)


def _normalize_repeated_chars(text: str) -> str:
    """ASR ノイズで生まれる連続重複文字を去重する。

    ReazonSpeech NeMo の subword 重複出力 (例: 「ほほとんど」「ダエットをお客様」)
    のうち、 **同一文字 2 連続** は 1 文字に圧縮する。 **3 連続以上** は意図的な
    強調 (例: 「あああ」「うううん」) と見なして保持する。

    例:
        「ほほとんど」 → 「ほとんど」
        「めめんたる」 → 「めんたる」
        「あああ」 → 「あああ」 (3 連続は保持)
    """
    if not text or len(text) < 2:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # 同一文字の連続をカウント
        j = i
        while j < n and text[j] == text[i]:
            j += 1
        run_len = j - i
        if run_len == 2:
            # 2 連続 → 1 文字に圧縮
            out.append(text[i])
        else:
            # 1 文字 or 3 連続以上はそのまま
            out.append(text[i] * run_len)
        i = j
    return "".join(out)


def words_to_segments(
    words: list[dict],
    max_chars: int = 12,
    max_gap: float = 0.4,
    lead_time: float = 0.05,
    tail_time: float = 0.20,
) -> list[dict]:
    """単語リストを字幕表示用のセグメントへ「意味のかたまり」 chunk 分割する。

    OpenSpec: subtitle-meaning-chunking

    3 階層の chunk 境界判定:
        1. 強境界 (必ず flush): word.text 末尾が「。」「、」「!」「?」
        2. 中境界 (flush): 次 word との gap ≥ max_gap (デフォルト 0.4 秒)
        3. 弱境界 (条件付き flush): chunk 文字数 ≥ max_chars

    clamp_oversized_word_ends で `_orig_end` を持つ word (ASR ノイズで word.text と
    実発話が一致しない) は **独立 chunk として隔離** する (前後 word と結合しない)。

    word.text は `_normalize_repeated_chars` で重複文字を去重してから処理する。

    視認性向上: 字幕の開始を lead_time だけ前倒し、 終わりを tail_time だけ後ろに伸ばす。
    """
    if not words:
        return []

    # 入力 word の text を正規化 (重複文字去重)
    normalized = []
    for w in words:
        text = _normalize_repeated_chars(w.get("text", ""))
        normalized.append({**w, "text": text})
    words = normalized

    segments = []
    current_words: list[dict] = []
    current_text = ""

    def flush():
        nonlocal current_words, current_text
        if not current_words:
            return
        segments.append({
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": current_text.strip(),
            "words": list(current_words),
        })
        current_words = []
        current_text = ""

    def _gap_before(next_word: dict) -> float:
        if not current_words:
            return 0.0
        cur = current_words[-1]
        cur_end = cur.get("_orig_end", cur["end"])
        return next_word["start"] - cur_end

    for w in words:
        text = w["text"]
        is_clamped = "_orig_end" in w

        # clamp 済み word は独立 chunk: 前 chunk を flush してから単独で flush
        if is_clamped:
            flush()
            current_words.append(w)
            current_text += text
            flush()
            continue

        # 中境界: gap ≥ max_gap
        if current_words and _gap_before(w) >= max_gap:
            flush()

        # 弱境界: chunk 文字数が max_chars を超える
        # (新規 word を加える前に判定し、 超えるなら flush)
        if current_words and len(current_text) + len(text) > max_chars:
            flush()

        current_words.append(w)
        current_text += text

        # 強境界: word.text 末尾が文末記号 (「、」 は弱境界扱いで flush しない: 短い断片
        # を量産する副作用があるため、 past change で確立した設計を踏襲)
        if text and text[-1] in "。!?！？.":
            flush()

    flush()

    # 隣接セグメント間の重複テキスト除去（Whisperチャンク境界での再記述を解消）
    segments = _dedupe_adjacent_overlaps(segments)
    # 1 文字 dialogue (clamp 済みでない) を隣接と統合する後処理
    segments = _merge_orphan_chars(segments, max_chars=max_chars * 2)

    # 視認性向上: lead_time だけ前倒し / tail_time だけ後ろに伸ばす
    # ただし隣のセグメントと被らないよう調整
    for i, seg in enumerate(segments):
        if i > 0:
            prev_end = segments[i - 1]["end"]
            min_start = prev_end + 0.01
        else:
            min_start = 0.0
        seg["start"] = max(min_start, seg["start"] - lead_time)

        next_start = segments[i + 1]["start"] if i + 1 < len(segments) else None
        candidate_end = seg["end"] + tail_time
        if next_start is not None:
            candidate_end = min(candidate_end, next_start - 0.01)
        seg["end"] = max(seg["end"], candidate_end)

    return segments


def _dedupe_adjacent_overlaps(segments: list[dict]) -> list[dict]:
    """隣接セグメント間の重複テキストを除去する（3パターン）：
    1. 後段の先頭が前段の末尾と一致 → 後段から先頭の重複を除去
    2. 後段全体が前段の部分文字列 → 後段を破棄
    3. 後段の前半 50%以上が前段に含まれる → 後段を破棄
    """
    if len(segments) < 2:
        return segments
    out = [dict(segments[0])]
    for seg in segments[1:]:
        prev = out[-1]
        prev_text = prev.get("text", "").strip()
        cur_text = seg.get("text", "").strip()
        if not cur_text:
            continue

        # パターン2: 後段全体が前段に含まれる
        if len(cur_text) >= 3 and cur_text in prev_text:
            continue

        # パターン3: 後段の先頭半分以上が前段に含まれる場合は後段破棄
        half = max(3, len(cur_text) // 2)
        if half >= 3 and cur_text[:half] in prev_text:
            # 重複部分のみ後段から取り除いて残りを採用、空なら破棄
            remaining = cur_text[half:].strip()
            if len(remaining) < 3:
                continue
            new_seg = dict(seg)
            new_seg["text"] = remaining
            out.append(new_seg)
            continue

        # パターン1: 末尾と先頭の最長一致（2〜20文字）
        max_len = min(len(prev_text), len(cur_text), 20)
        overlap = 0
        for i in range(max_len, 1, -1):
            if prev_text.endswith(cur_text[:i]):
                overlap = i
                break
        if overlap > 0:
            new_text = cur_text[overlap:].strip()
            if not new_text:
                continue
            new_seg = dict(seg)
            new_seg["text"] = new_text
            out.append(new_seg)
        else:
            out.append(dict(seg))
    return out


def _merge_orphan_chars(
    segments: list[dict],
    max_chars: int = 24,
) -> list[dict]:
    """1 文字 dialogue を隣接 dialogue に統合する後処理。

    clamp 済み word に由来する dialogue (元 word に `_orig_end` がある) は隔離維持
    する必要があるため、 「clamp 済み word を含む dialogue」 は統合対象外。

    統合条件:
    - 単一 dialogue の text が 1 文字
    - 含まれる word が clamp 済みでない
    - 統合後の合計が max_chars 以下
    - 前段が句点 (「。」「!」「?」) で終わっていない
    """
    if len(segments) < 2:
        return segments
    out: list[dict] = [dict(segments[0])]
    for seg in segments[1:]:
        prev = out[-1]
        prev_text = prev.get("text", "").strip()
        cur_text = seg.get("text", "").strip()
        cur_words = seg.get("words") or []
        prev_words = prev.get("words") or []

        # clamp 済み word を含む dialogue は隔離 (統合しない)
        has_clamped_cur = any("_orig_end" in w for w in cur_words)
        has_clamped_prev = any("_orig_end" in w for w in prev_words)

        # 統合候補は cur が 1 文字かつ両側 clamp なしの場合のみ
        is_orphan = (
            len(cur_text) == 1
            and not has_clamped_cur
            and not has_clamped_prev
        )
        combined_len = len(prev_text) + len(cur_text)
        prev_ends_sentence = prev_text and prev_text[-1] in "。！？!?."

        if is_orphan and not prev_ends_sentence and combined_len <= max_chars:
            prev["end"] = seg["end"]
            prev["text"] = (prev_text + cur_text).strip()
            prev["words"] = list(prev_words) + list(cur_words)
        else:
            out.append(dict(seg))
    return out


def _ass_time(seconds: float) -> str:
    """秒数を ASS タイムスタンプ形式 (H:MM:SS.cs) に変換"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_color(hex_color: str) -> str:
    """#RRGGBB を ASS の &HBBGGRR& 形式に変換"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "&H00FFFFFF&"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&"


def segments_to_ass(
    segments: list[dict],
    font_size: int = 22,
    position: str = "bottom",
    primary_color: str = "#FFFFFF",
    karaoke_color: str = "#FFFF00",
    keywords: list[str] | None = None,
    keyword_color: str = "#FFD700",
    video_width: int = 1080,
    video_height: int = 1920,
    motion_style: str = "karaoke",
) -> str:
    """単語タイムスタンプ付きセグメントから ASS 字幕（キネティックモーション）を生成する。

    Args:
        segments: words を含むセグメントリスト
        font_size: フォントサイズ
        position: "bottom" or "center"
        primary_color: 通常色 (#RRGGBB)
        karaoke_color: カラオケで「次に話される」色（SecondaryColour）
        keywords: 強調表示するキーワード
        keyword_color: キーワードの色
        video_width, video_height: ビデオサイズ（ASS の PlayRes）
        motion_style: 字幕の動き
            "none"     : 動きなし（静止表示、キーワード色のみ）
            "karaoke"  : 既存のカラオケ風カラースイープ（\\kf）
            "fade"     : カラオケ + 行全体のソフトフェードイン/アウト（上品）
            "pop"      : カラオケ + 語ごとの控えめなスケール pop（元気め）
            WhisperX の高精度 word timestamp 前提。\\t の時刻は行頭からの
            ミリ秒、\\kf の duration はセンチ秒で別単位なので混同しないこと。

    Returns:
        ASS ファイル文字列
    """
    keywords_set = set(k for k in (keywords or []) if k)
    primary_ass = _ass_color(primary_color)
    karaoke_ass = _ass_color(karaoke_color)
    keyword_ass = _ass_color(keyword_color)
    alignment = 2 if position == "bottom" else 5

    # PlayRes は 1080p 基準で固定。libass が動画解像度に自動スケールするため、
    # font_size はユーザー指定値（16/22/30）をそのまま 1080p 基準として使える。
    play_res_y = 1080
    play_res_x = max(1, int(round(play_res_y * video_width / max(video_height, 1))))
    # 1080p 基準でのフォント・アウトライン・マージン
    effective_font = max(font_size, 36)  # 最低36（読みやすさ確保）
    effective_outline = 3
    effective_margin_v = 60

    style_line = (
        f"Style: Default,Noto Sans CJK JP,{effective_font},"
        f"{karaoke_ass},{primary_ass},&H00000000,&HC0000000,"
        f"-1,0,0,0,100,100,0,0,3,{effective_outline},0,{alignment},20,20,{effective_margin_v},1"
    )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    motion = motion_style if motion_style in ("none", "karaoke", "fade", "pop") else "karaoke"
    # 行全体のソフトフェード（ms）。fade のみ適用。
    line_lead = "{\\fad(120,80)}" if motion == "fade" else ""
    # pop の語スケール演出（ms, 行頭からの相対時刻）
    POP_RISE_MS, POP_FALL_MS, POP_SCALE = 90, 230, 113

    dialogues: list[str] = []
    for seg in segments:
        seg_words = seg.get("words") or []
        # words が無い seg はスキップ（カット駆動のため、word が remap で全消失した区間は
        # 動画からも消えている。seg.text を描画すると phantom 字幕になるので出さない）。
        if not seg_words:
            continue

        line_start = seg_words[0]["start"]
        parts: list[str] = []
        for w in seg_words:
            text = w.get("text") or w.get("word") or ""
            if not text:
                continue
            duration_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            off_ms = max(0, int(round((w["start"] - line_start) * 1000)))

            tags = "" if motion == "none" else f"\\kf{duration_cs}"
            if motion == "pop":
                tags += (
                    f"\\fscx100\\fscy100"
                    f"\\t({off_ms},{off_ms + POP_RISE_MS},\\fscx{POP_SCALE}\\fscy{POP_SCALE})"
                    f"\\t({off_ms + POP_RISE_MS},{off_ms + POP_FALL_MS},\\fscx100\\fscy100)"
                )

            normalized = text.strip().strip("、。！？!?.,")
            if normalized in keywords_set:
                parts.append(f"{{{tags}\\c{keyword_ass}}}{text}{{\\c{primary_ass}}}")
            elif tags:
                parts.append(f"{{{tags}}}{text}")
            else:
                parts.append(text)
        if not parts:
            continue
        start_t = _ass_time(seg_words[0]["start"])
        end_t = _ass_time(seg_words[-1]["end"])
        dialogues.append(
            f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{line_lead}{''.join(parts)}"
        )

    return header + "\n".join(dialogues) + "\n"


import re


def apply_keyword_highlight(text: str, keywords: list[str], color: str = "#FFD700") -> str:
    """テキスト内のキーワードを ASS/SRT 用の color font タグで囲む。

    Args:
        text: 対象テキスト
        keywords: ハイライトするキーワード
        color: ハイライト色（HTML #RRGGBB）

    Returns:
        キーワードを <font color="..."> で囲んだテキスト
    """
    if not keywords or not text:
        return text
    sorted_kw = sorted({k for k in keywords if k}, key=len, reverse=True)
    if not sorted_kw:
        return text
    pattern = "|".join(re.escape(k) for k in sorted_kw)
    return re.sub(
        f"({pattern})",
        rf'<font color="{color}">\1</font>',
        text,
    )


from .asr import transcribe_with_words  # noqa: F401  re-export for backward compat


def transcribe_audio(audio_path: str, srt_output_path: str, initial_prompt: str | None = None) -> str:
    """音声を文字起こしし、SRTファイルを生成"""
    _words, segments, _backend = transcribe_with_words(audio_path, initial_prompt=initial_prompt)
    srt_content = segments_to_srt(segments)
    Path(srt_output_path).write_text(srt_content, encoding="utf-8")
    return srt_output_path
