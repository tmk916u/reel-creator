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


def transcribe_audio(audio_path: str, srt_output_path: str) -> str:
    """faster-whisperで音声を文字起こしし、SRTファイルを生成"""
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(audio_path, language="ja")

    segments = []
    for seg in segments_iter:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

    srt_content = segments_to_srt(segments)
    Path(srt_output_path).write_text(srt_content, encoding="utf-8")

    return srt_output_path
