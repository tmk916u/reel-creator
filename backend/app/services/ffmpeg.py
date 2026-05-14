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


def cut_and_concat(
    video_path: str,
    segments: list[dict],
    output_path: str,
    audio_fade: float = 0.04,
) -> str:
    """有音セグメントをカットして結合。

    各セグメントの先頭・末尾に短い音声フェードを掛けることで、
    カット境界のクリック・ぶつ切り感を軽減する。
    """
    if not segments:
        raise ValueError("No segments to concatenate")

    workdir = Path(output_path).parent / "segments"
    workdir.mkdir(exist_ok=True)
    concat_list = workdir / "concat.txt"

    segment_files = []
    for i, seg in enumerate(segments):
        seg_file = str(workdir / f"seg_{i:04d}.mp4")
        seg_dur = max(0.0, seg["end"] - seg["start"])
        fade_d = min(audio_fade, seg_dur / 3) if seg_dur > 0 else 0
        fade_out_st = max(0.0, seg_dur - fade_d)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seg["start"]),
            "-i", video_path,
            "-t", f"{seg_dur:.3f}",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
        ]
        if fade_d > 0:
            cmd += [
                "-af",
                f"afade=t=in:d={fade_d:.3f},afade=t=out:d={fade_d:.3f}:st={fade_out_st:.3f}",
            ]
        cmd.append(seg_file)
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
    """SRT/ASS字幕を動画に焼き込む。.ass はそのままスタイル適用、.srt は force_style を使用"""
    is_ass = srt_path.lower().endswith(".ass")

    if is_ass:
        vf = f"subtitles={srt_path}"
    else:
        alignment = 2 if position == "bottom" else 5
        color_hex = "&H00FFFFFF" if color == "white" else "&H0000FFFF"

        style = (
            f"FontSize={font_size},"
            f"PrimaryColour={color_hex},"
            f"OutlineColour=&H00000000,"
            f"BackColour=&HC0000000,"
            f"Alignment={alignment},"
            f"BorderStyle=3,"
            f"Outline=3,"
            f"Shadow=0,"
            f"MarginV=40,"
            f"Bold=1,"
            f"FontName=Noto Sans CJK JP"
        )
        vf = f"subtitles={srt_path}:force_style='{style}'"

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg subtitle burn failed: {result.stderr}")

    return output_path


def overlay_hook_text(
    video_path: str,
    output_path: str,
    hook_text: str,
    duration: float = 3.0,
    font_size: int = 80,
) -> str:
    """動画の冒頭にフックテキストをオーバーレイ表示する。

    Args:
        video_path: 入力動画
        output_path: 出力動画
        hook_text: 表示するフックテキスト
        duration: フックを表示する秒数（0からこの時間まで）
        font_size: フォントサイズ（px）
    """
    if not hook_text.strip():
        # フックなし → そのままコピー
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    # ffmpeg drawtext 用にエスケープ問題を回避するため textfile を使う
    workdir = Path(output_path).parent
    hook_file = workdir / "hook.txt"
    hook_file.write_text(hook_text, encoding="utf-8")

    font_file = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

    drawtext = (
        f"drawtext=textfile={hook_file}"
        f":fontfile={font_file}"
        f":fontsize={font_size}"
        f":fontcolor=white"
        f":box=1:boxcolor=black@0.8:boxborderw=30"
        f":x=(w-text_w)/2"
        f":y=h*0.18"
        f":enable='lt(t\\,{duration})'"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg hook overlay failed: {result.stderr}")

    return output_path


def overlay_cta_text(
    video_path: str,
    output_path: str,
    cta_text: str,
    duration: float = 3.0,
    font_size: int = 110,
) -> str:
    """動画の末尾にCTAテキストをオーバーレイ表示する。点滅効果付き。"""
    if not cta_text.strip():
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    total_dur = get_video_duration(video_path)
    start_t = max(0.0, total_dur - duration)

    workdir = Path(output_path).parent
    cta_file = workdir / "cta.txt"
    cta_file.write_text(cta_text, encoding="utf-8")

    font_file = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

    # 2層描画: 黒下地（やや大）＋黄色文字（点滅: 0.4秒周期）で目立たせる
    drawtext_bg = (
        f"drawtext=textfile={cta_file}"
        f":fontfile={font_file}"
        f":fontsize={font_size}"
        f":fontcolor=black"
        f":box=1:boxcolor=black@0.9:boxborderw=35"
        f":x=(w-text_w)/2"
        f":y=h*0.42"
        f":enable='gt(t\\,{start_t:.3f})'"
    )
    drawtext_fg = (
        f"drawtext=textfile={cta_file}"
        f":fontfile={font_file}"
        f":fontsize={font_size}"
        f":fontcolor=yellow"
        f":borderw=4:bordercolor=black"
        f":x=(w-text_w)/2"
        f":y=h*0.42"
        # 点滅: t-start_t を 0.5 秒で割って偶数のときだけ表示
        f":alpha='if(gt(t\\,{start_t:.3f})\\,if(eq(mod(floor((t-{start_t:.3f})*2)\\,2)\\,0)\\,1\\,0.5)\\,0)'"
    )
    vf = drawtext_bg + "," + drawtext_fg

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg cta overlay failed: {result.stderr}")

    return output_path


_CIRCLED_NUMBERS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]


def overlay_topic_numbers(
    video_path: str,
    output_path: str,
    topics: list[dict],
    number_size: int = 150,
    label_size: int = 60,
) -> str:
    """画面右上にトピック番号 ①②③ をオーバーレイ表示する。

    Args:
        topics: [{"index": int, "start": float, "end": float, "label": str}, ...]
    """
    if not topics:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    workdir = Path(output_path).parent
    font_file = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

    filters = []
    for i, t in enumerate(topics):
        idx = int(t.get("index", i + 1))
        if not (1 <= idx <= len(_CIRCLED_NUMBERS)):
            continue
        number_char = _CIRCLED_NUMBERS[idx - 1]
        start_t = float(t["start"])
        end_t = float(t["end"])
        label = (t.get("label") or "").strip()

        # 番号テキスト（右上の大きい数字、黄色背景＋黒文字で目立たせる）
        num_file = workdir / f"topic_num_{i}.txt"
        num_file.write_text(number_char, encoding="utf-8")
        filters.append(
            f"drawtext=textfile={num_file}"
            f":fontfile={font_file}"
            f":fontsize={number_size}"
            f":fontcolor=black"
            f":box=1:boxcolor=yellow@0.95:boxborderw=20"
            f":x=w-text_w-50:y=80"
            f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
        )

        # ラベル（番号の下、ピンク背景の白文字）
        if label:
            label_file = workdir / f"topic_label_{i}.txt"
            label_file.write_text(label, encoding="utf-8")
            filters.append(
                f"drawtext=textfile={label_file}"
                f":fontfile={font_file}"
                f":fontsize={label_size}"
                f":fontcolor=white"
                f":borderw=3:bordercolor=black"
                f":box=1:boxcolor=0xE91E63@0.92:boxborderw=18"
                f":x=w-text_w-50:y=80+{number_size}+50"
                f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
            )

    if not filters:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg topic overlay failed: {result.stderr}")

    return output_path


def mix_bgm(
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float = 0.12,
    bgm_fade: float = 1.5,
) -> str:
    """動画に BGM を合成する。BGM 音量を下げて話し声と被らないように。

    Args:
        bgm_volume: BGM 音量 (0.0-1.0, 0.1〜0.15 推奨)
        bgm_fade: BGM のフェードイン/アウト秒数
    """
    total_dur = get_video_duration(video_path)
    fade_out_st = max(0.0, total_dur - bgm_fade)

    afilter = (
        f"[1:a]aloop=loop=-1:size=2e9,volume={bgm_volume},"
        f"afade=t=in:d={bgm_fade:.2f},"
        f"afade=t=out:d={bgm_fade:.2f}:st={fade_out_st:.3f},"
        f"atrim=duration={total_dur:.3f}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", bgm_path,
        "-filter_complex", afilter,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg bgm mix failed: {result.stderr}")

    return output_path
