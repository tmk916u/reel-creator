# backend/app/services/subtitle.py
from pathlib import Path


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


def words_to_segments(
    words: list[dict],
    max_chars: int = 18,
    max_gap: float = 0.6,
    lead_time: float = 0.05,
    tail_time: float = 0.20,
) -> list[dict]:
    """単語リストを字幕表示用のセグメントへグループ化する。

    句読点・長い無音・最大文字数で区切る。
    視聴者が読みやすいように、字幕の開始を lead_time だけ早め、終わりを tail_time だけ伸ばす。
    """
    if not words:
        return []

    segments = []
    current_words: list[dict] = []
    current_text = ""

    def flush():
        if not current_words:
            return
        segments.append({
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": current_text.strip(),
            "words": list(current_words),
        })

    for i, w in enumerate(words):
        text = w["text"]
        gap = w["start"] - current_words[-1]["end"] if current_words else 0.0

        if current_words and (gap > max_gap or len(current_text) + len(text) > max_chars):
            flush()
            current_words = []
            current_text = ""

        current_words.append(w)
        current_text += text

        if text and text[-1] in "、。！？!?.":
            flush()
            current_words = []
            current_text = ""

    if current_words:
        flush()

    # 隣接セグメント間の重複テキスト除去（Whisperチャンク境界での再記述を解消）
    segments = _dedupe_adjacent_overlaps(segments)
    # 短すぎるセグメントを次の/前のセグメントに統合（ぶつ切り感の解消）
    segments = _merge_short_segments(segments, min_dur=0.6, max_chars=max(max_chars, 24))

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


def _merge_short_segments(
    segments: list[dict],
    min_dur: float = 0.6,
    max_chars: int = 24,
) -> list[dict]:
    """短すぎる/フラグメント的なセグメントを隣のセグメントに統合する。

    3パターンで統合判定:
    1. 両方が短時間 (<min_dur) + 合計が短い + 近い → 統合
    2. どちらかが極端に短い文字数 (<5文字) + 合計が読める長さ + 大きすぎないギャップ → 統合
    3. 前段が句読点で終わっている場合は統合しない（文の区切り尊重）
    """
    if len(segments) < 2:
        return segments
    out: list[dict] = [dict(segments[0])]
    for seg in segments[1:]:
        prev = out[-1]
        prev_text = prev.get("text", "").strip()
        cur_text = seg.get("text", "").strip()
        prev_dur = prev["end"] - prev["start"]
        cur_dur = seg["end"] - seg["start"]
        combined_len = len(prev_text) + len(cur_text)
        gap = seg["start"] - prev["end"]

        # 前段が句読点で終わっていれば文の終わり → 統合しない
        prev_ends_with_punct = prev_text and prev_text[-1] in "、。！？!?."

        either_tiny = len(prev_text) < 5 or len(cur_text) < 5
        both_short = prev_dur < min_dur and cur_dur < min_dur

        should_merge = False
        if not prev_ends_with_punct:
            if both_short and combined_len <= max_chars and gap < 0.8:
                should_merge = True
            elif either_tiny and combined_len <= 30 and gap < 3.0:
                # フラグメント（1〜4文字）は3秒以内のギャップなら統合
                should_merge = True

        if should_merge:
            prev["end"] = seg["end"]
            prev["text"] = (prev_text + cur_text).strip()
            if "words" in prev or "words" in seg:
                prev["words"] = list(prev.get("words", [])) + list(seg.get("words", []))
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
) -> str:
    """単語タイムスタンプ付きセグメントから ASS 字幕（カラオケ風モーション）を生成する。

    Args:
        segments: words を含むセグメントリスト
        font_size: フォントサイズ
        position: "bottom" or "center"
        primary_color: 通常色 (#RRGGBB)
        karaoke_color: カラオケで「次に話される」色（SecondaryColour）
        keywords: 強調表示するキーワード
        keyword_color: キーワードの色
        video_width, video_height: ビデオサイズ（ASS の PlayRes）

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

    dialogues: list[str] = []
    for seg in segments:
        seg_words = seg.get("words") or []
        if not seg_words:
            continue
        parts: list[str] = []
        for w in seg_words:
            duration_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            text = w["text"]
            if not text:
                continue
            normalized = text.strip().strip("、。！？!?.,")
            if normalized in keywords_set:
                parts.append(
                    f"{{\\kf{duration_cs}\\c{keyword_ass}}}{text}{{\\c{primary_ass}}}"
                )
            else:
                parts.append(f"{{\\kf{duration_cs}}}{text}")
        if not parts:
            continue
        start_t = _ass_time(seg_words[0]["start"])
        end_t = _ass_time(seg_words[-1]["end"])
        dialogues.append(
            f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{''.join(parts)}"
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


_DEFAULT_INITIAL_PROMPT = "日本語で話している動画の文字起こしです。"


from functools import lru_cache


@lru_cache(maxsize=2)
def _load_whisperx_model(model_size: str, language: str, initial_prompt: str):
    """WhisperX のロード済みモデルをキャッシュして返す（プロセス内で再利用）。"""
    import whisperx
    return whisperx.load_model(
        model_size, device="cpu", compute_type="int8",
        language=language,
        asr_options={"initial_prompt": initial_prompt},
    )


@lru_cache(maxsize=1)
def _load_whisperx_align_model(language_code: str):
    """WhisperX のアライメントモデルをキャッシュして返す。"""
    import whisperx
    return whisperx.load_align_model(language_code=language_code, device="cpu")


@lru_cache(maxsize=2)
def _load_faster_whisper_model(model_size: str):
    """faster-whisper のロード済みモデルをキャッシュ。"""
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def _transcribe_with_whisperx(
    audio_path: str,
    initial_prompt: str,
    model_size: str,
) -> tuple[list[dict], list[dict]] | None:
    """WhisperX (faster-whisper + wav2vec2 forced alignment) で文字起こし。

    成功時 (words, segments)、失敗時 None を返す。
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        import whisperx
        # torch 2.6+ の weights_only=True デフォルトに対応:
        # pyannote 内で使う omegaconf.ListConfig などを safe globals に登録
        try:
            import torch.serialization
            from omegaconf.listconfig import ListConfig
            from omegaconf.dictconfig import DictConfig
            from omegaconf.base import ContainerMetadata, Metadata
            from omegaconf.nodes import AnyNode
            import typing
            torch.serialization.add_safe_globals([
                ListConfig, DictConfig, ContainerMetadata, Metadata, AnyNode,
                typing.Any, typing.List, typing.Dict, typing.Tuple, typing.Optional,
                typing.Union, typing.Sequence, typing.Mapping,
            ])
        except Exception as patch_e:
            logger.warning("WhisperX safe-globals patch skipped: %s", patch_e)
    except Exception as e:
        logger.warning("WhisperX not available: %s", e)
        return None

    try:
        audio = whisperx.load_audio(audio_path)
        model = _load_whisperx_model(model_size, "ja", initial_prompt)
        result = model.transcribe(audio, language="ja", batch_size=4)

        # 単語アライメント（wav2vec2 forced alignment）
        align_model, metadata = _load_whisperx_align_model("ja")
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device="cpu",
            return_char_alignments=False,
        )

        words: list[dict] = []
        segments: list[dict] = []
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": (seg.get("text") or "").strip(),
            })
            for w in seg.get("words", []):
                if "start" not in w or "end" not in w:
                    continue
                words.append({
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                    "text": w.get("word", "") or w.get("text", ""),
                })
        logger.info("WhisperX: %d segments, %d aligned words", len(segments), len(words))
        return words, segments
    except Exception as e:
        logger.warning("WhisperX failed, falling back to faster-whisper: %s", e)
        return None


def transcribe_with_words(
    audio_path: str,
    initial_prompt: str | None = None,
    model_size: str = "medium",
) -> tuple[list[dict], list[dict]]:
    """音声を文字起こしし、単語レベルとセグメントレベルの transcript を返す。

    WhisperX を優先利用（forced alignment で単語境界の精度が高い）。
    失敗時は faster-whisper の word_timestamps にフォールバック。
    """
    prompt = initial_prompt or _DEFAULT_INITIAL_PROMPT

    # 優先: WhisperX
    result = _transcribe_with_whisperx(audio_path, prompt, model_size)
    if result is not None:
        return result

    # フォールバック: faster-whisper（キャッシュ済みモデルを利用）
    model = _load_faster_whisper_model(model_size)
    segments_iter, _info = model.transcribe(
        audio_path,
        language="ja",
        word_timestamps=True,
        initial_prompt=prompt,
    )

    words: list[dict] = []
    segments: list[dict] = []
    for seg in segments_iter:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })
        if seg.words:
            for w in seg.words:
                words.append({
                    "start": w.start,
                    "end": w.end,
                    "text": w.word,
                })

    return words, segments


def transcribe_audio(audio_path: str, srt_output_path: str, initial_prompt: str | None = None) -> str:
    """faster-whisperで音声を文字起こしし、SRTファイルを生成"""
    _words, segments = transcribe_with_words(audio_path, initial_prompt=initial_prompt)
    srt_content = segments_to_srt(segments)
    Path(srt_output_path).write_text(srt_content, encoding="utf-8")
    return srt_output_path
