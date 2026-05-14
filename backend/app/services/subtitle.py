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
    max_chars: int = 30,
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


def transcribe_with_words(audio_path: str) -> tuple[list[dict], list[dict]]:
    """faster-whisperで音声を文字起こしし、単語レベルとセグメントレベルの transcript を返す。

    Returns:
        (words, segments) のタプル。
        words: [{"start": float, "end": float, "text": str}, ...]
        segments: [{"start": float, "end": float, "text": str}, ...]
    """
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_iter, _info = model.transcribe(
        audio_path,
        language="ja",
        word_timestamps=True,
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


def transcribe_audio(audio_path: str, srt_output_path: str) -> str:
    """faster-whisperで音声を文字起こしし、SRTファイルを生成"""
    _words, segments = transcribe_with_words(audio_path)
    srt_content = segments_to_srt(segments)
    Path(srt_output_path).write_text(srt_content, encoding="utf-8")
    return srt_output_path
