import subprocess
import json
import os
from pathlib import Path


def get_video_duration(filepath: str) -> float:
    """FFprobeで動画の長さ（秒）を取得"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_audio(video_path: str, output_path: str) -> str:
    """動画から音声をWAVで抽出"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")
    return output_path


def detect_silence(audio_path: str, threshold: float = -30.0, min_duration: float = 0.5) -> list[dict]:
    """FFmpegのsilencedetectフィルタで無音区間を検出"""
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silences = []
    silence_start = None
    for line in stderr.split("\n"):
        if "silence_start:" in line:
            silence_start = float(line.split("silence_start:")[1].strip().split()[0])
        elif "silence_end:" in line and silence_start is not None:
            parts = line.split("silence_end:")[1].strip().split()
            silence_end = float(parts[0])
            silences.append({"start": silence_start, "end": silence_end})
            silence_start = None

    return silences


def cut_and_concat(video_path: str, segments: list[dict], output_path: str) -> str:
    """有音セグメントをカットして結合"""
    if not segments:
        raise ValueError("No segments to concatenate")

    workdir = Path(output_path).parent / "segments"
    workdir.mkdir(exist_ok=True)
    concat_list = workdir / "concat.txt"

    segment_files = []
    for i, seg in enumerate(segments):
        seg_file = str(workdir / f"seg_{i:04d}.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(seg["start"]),
            "-to", str(seg["end"]),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            seg_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg cut failed for segment {i}: {result.stderr}")
        segment_files.append(seg_file)

    with open(concat_list, "w") as f:
        for sf in segment_files:
            f.write(f"file '{sf}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")

    return output_path


def burn_subtitles(video_path: str, srt_path: str, output_path: str,
                   font_size: int = 20, position: str = "bottom",
                   color: str = "white") -> str:
    """SRT字幕を動画に焼き込む"""
    alignment = 2 if position == "bottom" else 5  # ASS alignment
    color_hex = "&H00FFFFFF" if color == "white" else "&H0000FFFF"

    style = (
        f"FontSize={font_size},"
        f"PrimaryColour={color_hex},"
        f"Alignment={alignment},"
        f"BorderStyle=3,"
        f"Outline=1,"
        f"Shadow=0,"
        f"MarginV=30,"
        f"FontName=Noto Sans CJK JP"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg subtitle burn failed: {result.stderr}")

    return output_path
