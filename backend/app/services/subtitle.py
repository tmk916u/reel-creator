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
) -> list[dict]:
    """単語リストを字幕表示用のセグメントへグループ化する。

    句読点・長い無音・最大文字数で区切る。
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

    return segments


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
            torch.serialization.add_safe_globals([
                ListConfig, DictConfig, ContainerMetadata, Metadata, AnyNode,
            ])
        except Exception as patch_e:
            logger.warning("WhisperX safe-globals patch skipped: %s", patch_e)
    except Exception as e:
        logger.warning("WhisperX not available: %s", e)
        return None

    try:
        audio = whisperx.load_audio(audio_path)
        model = whisperx.load_model(
            model_size, device="cpu", compute_type="int8",
            language="ja",
            asr_options={"initial_prompt": initial_prompt},
        )
        result = model.transcribe(audio, language="ja", batch_size=4)

        # 単語アライメント（wav2vec2 forced alignment）
        align_model, metadata = whisperx.load_align_model(
            language_code="ja", device="cpu",
        )
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

    # フォールバック: faster-whisper
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
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
