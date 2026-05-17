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


def extract_audio(video_path: str, output_path: str, preprocess: bool = True) -> str:
    """動画から音声を WAV で抽出する（既定で前処理あり）。

    preprocess=True の場合、ffmpeg の audio filter で以下を適用:
    - afftdn (FFT ベースのノイズ除去): ジム BGM や環境音の定常ノイズを軽減
    - dynaudnorm (動的音量正規化): 自撮りの声量ムラを平滑化
    これにより ASR (ReazonSpeech/WhisperX) の認識精度が安定する。
    """
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn"]
    if preprocess:
        # nr=12: 中程度の削減（声を潰さず BGM を軽減）
        # dynaudnorm p=0.95 f=200: 200ms フレームで動的正規化、ピーク95%
        cmd += ["-af", "afftdn=nr=12,dynaudnorm=p=0.95:f=200"]
    cmd += [
        "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr[-500:]}")
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


def _build_cut_concat_filter(
    segments: list[dict],
    audio_fade: float = 0.08,
    target_width: int = 1080,
    target_height: int = 1920,
    fps: int = 30,
) -> str:
    """cut_and_concat 用の filter_complex 文字列を組み立てる。

    各セグメントを scale+pad で target サイズに揃え、音声に短い fade を掛け、
    最後に concat フィルタで結合する。concat 出力には fps を明示し、
    libx264 の MB rate 検出が縦動画の displaymatrix で暴走するのを防ぐ。

    seg_dur < 3*audio_fade のときフェード長を dur/3 にクランプ、
    seg_dur=0 はフェードなし。
    """
    parts: list[str] = []
    concat_labels: list[str] = []
    # 解像度を揃えるための共通 video filter（scale + pad で 9:16 中央配置）
    vf_resize = (
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )
    for i, seg in enumerate(segments):
        start = float(seg["start"])
        end = float(seg["end"])
        dur = max(0.0, end - start)
        fade_d = min(audio_fade, dur / 3) if dur > 0 else 0.0
        fade_out_st = max(0.0, dur - fade_d)

        parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS,{vf_resize}[v{i}]"
        )
        if fade_d > 0:
            parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={fade_d:.3f},"
                f"afade=t=out:d={fade_d:.3f}:st={fade_out_st:.3f}[a{i}]"
            )
        else:
            parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
        concat_labels.append(f"[v{i}][a{i}]")
    n = len(segments)
    # concat 後に fps を明示。これで libx264 が level/MB rate 計算で誤計算するのを防ぐ
    parts.append(f"{''.join(concat_labels)}concat=n={n}:v=1:a=1[vcat][outa]")
    parts.append(f"[vcat]fps={fps}[outv]")
    return ";".join(parts)


def cut_and_concat(
    video_path: str,
    segments: list[dict],
    output_path: str,
    audio_fade: float = 0.08,
    target_width: int = 1080,
    target_height: int = 1920,
    fps: int = 30,
) -> str:
    """有音セグメントをカットして結合（リール解像度 1080x1920 にダウンスケール）。

    filter_complex の trim + atrim + concat を 1 パスの ffmpeg で実行する。
    4K 入力をそのまま処理するとメモリ消費が爆発し OOM でクラッシュするため、
    最終出力サイズに揃えてからエンコードする（リール用 1080x1920 既定）。
    """
    if not segments:
        raise ValueError("No segments to concatenate")

    filter_complex = _build_cut_concat_filter(
        segments, audio_fade, target_width, target_height, fps,
    )
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # stderr が巨大なので末尾だけ抜粋して例外メッセージに（先頭は ffmpeg バナーで情報が薄い）
        tail = "\n".join((result.stderr or "").splitlines()[-30:])
        raise RuntimeError(f"ffmpeg cut_and_concat failed:\n{tail}")
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


def mix_sfx_at_cuts(
    video_path: str,
    sfx_path: str,
    output_path: str,
    cut_timestamps_sec: list[float],
    sfx_volume: float = 0.15,
) -> str:
    """カット境界のタイムスタンプに効果音を重ねる。

    Args:
        cut_timestamps_sec: カット後動画の時間軸での境界秒数リスト
        sfx_volume: 効果音の音量 (0.0-1.0)
    """
    if not cut_timestamps_sec or not Path(sfx_path).exists():
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    # 各タイムスタンプに delay 適用した SFX トラックを作って amix
    filter_parts: list[str] = []
    mix_inputs: list[str] = ["[0:a]"]
    for i, t in enumerate(cut_timestamps_sec):
        delay_ms = max(0, int(t * 1000))
        filter_parts.append(
            f"[1:a]adelay={delay_ms}|{delay_ms},volume={sfx_volume}[sfx{i}]"
        )
        mix_inputs.append(f"[sfx{i}]")

    if not filter_parts:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    filter_complex = (
        ";".join(filter_parts)
        + f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", sfx_path,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg sfx mix failed: {result.stderr}")

    return output_path


_CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]


def _fit_overlay_text(
    text: str,
    base_size: int,
    max_width_px: int = 980,
    min_size: int = 40,
    max_chars_per_line: int = 14,
) -> tuple[str, int]:
    """オーバーレイテキスト(hook/cta)を画面幅に収めるため、必要に応じて
    改行を挿入し font_size を縮める。

    - text が 1 行で max_width_px に収まれば、base_size のまま 1 行
    - 縮めれば 1 行で収まる場合、font_size を縮めて 1 行
    - それでも収まらない場合、自然な助詞・句読点位置で 2 行に分割

    日本語フォントは「1文字 ≒ font_size px」と近似(等幅でないが目安)。

    Returns:
        (wrapped_text, effective_font_size)
    """
    text = text.strip()
    if not text:
        return text, base_size

    # 1 行のままで base_size を維持できるか
    if base_size * len(text) <= max_width_px and len(text) <= max_chars_per_line:
        return text, base_size

    # 1 行で font_size を縮めれば収まるか(短いテキストはこちら)
    if len(text) <= max_chars_per_line:
        new_size = max(min_size, max_width_px // max(1, len(text)))
        return text, min(base_size, new_size)

    # 2 行に分割。「、」「。」のような自然な区切りで分けたい
    breakers = set("、。！？!?,.")
    soft_breakers = set("はがをにでとのもからまでへやかな")
    mid = len(text) // 2
    best = None
    best_dist = len(text)
    # 強い区切り(句読点)を優先
    for i in range(1, len(text)):
        if text[i - 1] in breakers:
            d = abs(i - mid)
            if d < best_dist:
                best = i
                best_dist = d
    # 句読点が無ければ助詞でも可
    if best is None:
        for i in range(1, len(text)):
            if text[i - 1] in soft_breakers:
                d = abs(i - mid)
                if d < best_dist:
                    best = i
                    best_dist = d
    if best is None:
        best = mid

    line1 = text[:best]
    line2 = text[best:]
    longest = max(len(line1), len(line2))
    new_size = max(min_size, min(base_size, max_width_px // max(1, longest)))
    return f"{line1}\n{line2}", new_size


def apply_pipeline_combined(
    input_video: str,
    output_video: str,
    workdir: Path,
    *,
    subtitle_file: str | None = None,
    subtitle_force_style: str | None = None,  # for SRT
    topics: list[dict] | None = None,  # [{index, start, end, label}]
    topic_number_size: int = 150,
    topic_label_size: int = 60,
    hook_text: str | None = None,
    hook_duration: float = 3.0,
    hook_font_size: int = 80,
    cta_text: str | None = None,
    cta_duration: float = 3.0,
    cta_font_size: int = 80,  # 顔を隠さないサイズ。画面下部 y=h*0.82 に配置
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
    bgm_fade: float = 1.5,
    sfx_path: str | None = None,
    sfx_timestamps_sec: list[float] | None = None,
    sfx_volume: float = 0.15,
) -> str:
    """すべての動画オーバーレイ・音響処理を1つの ffmpeg パスでまとめて適用する。

    現状の chain（subtitle→topics→hook→cta→bgm）を 6 パスから 1 パスに圧縮。
    """
    font_file = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    total_dur = get_video_duration(input_video)

    # ====== 映像フィルタチェーン構築 ======
    video_filters: list[str] = []

    if subtitle_file:
        if subtitle_file.lower().endswith(".ass"):
            video_filters.append(f"subtitles={subtitle_file}")
        else:
            style = subtitle_force_style or ""
            if style:
                video_filters.append(f"subtitles={subtitle_file}:force_style='{style}'")
            else:
                video_filters.append(f"subtitles={subtitle_file}")

    # トピック番号
    if topics:
        for i, t in enumerate(topics):
            idx = int(t.get("index", i + 1))
            if not (1 <= idx <= len(_CIRCLED)):
                continue
            number_char = _CIRCLED[idx - 1]
            start_t = float(t["start"])
            end_t = float(t["end"])
            label = (t.get("label") or "").strip()
            num_file = workdir / f"topic_num_{i}.txt"
            num_file.write_text(number_char, encoding="utf-8")
            video_filters.append(
                f"drawtext=textfile={num_file}"
                f":fontfile={font_file}:fontsize={topic_number_size}"
                f":fontcolor=black:box=1:boxcolor=yellow@0.95:boxborderw=20"
                f":x=w-text_w-50:y=80"
                f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
            )
            if label:
                label_file = workdir / f"topic_label_{i}.txt"
                label_file.write_text(label, encoding="utf-8")
                video_filters.append(
                    f"drawtext=textfile={label_file}"
                    f":fontfile={font_file}:fontsize={topic_label_size}"
                    f":fontcolor=white:borderw=3:bordercolor=black"
                    f":box=1:boxcolor=0xE91E63@0.92:boxborderw=18"
                    f":x=w-text_w-50:y=80+{topic_number_size}+50"
                    f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
                )

    # 冒頭フック
    if hook_text and hook_text.strip():
        hook_file = workdir / "hook.txt"
        wrapped_hook, hook_size = _fit_overlay_text(hook_text, hook_font_size)
        hook_file.write_text(wrapped_hook, encoding="utf-8")
        video_filters.append(
            f"drawtext=textfile={hook_file}"
            f":fontfile={font_file}:fontsize={hook_size}"
            f":fontcolor=white:box=1:boxcolor=black@0.8:boxborderw=30"
            f":x=(w-text_w)/2:y=h*0.18"
            f":enable='lt(t\\,{hook_duration:.3f})'"
        )

    # 末尾CTA（点滅）
    if cta_text and cta_text.strip():
        cta_file = workdir / "cta.txt"
        wrapped_cta, cta_size = _fit_overlay_text(cta_text, cta_font_size)
        cta_file.write_text(wrapped_cta, encoding="utf-8")
        cta_start = max(0.0, total_dur - cta_duration)
        video_filters.append(
            f"drawtext=textfile={cta_file}"
            f":fontfile={font_file}:fontsize={cta_size}"
            f":fontcolor=black:box=1:boxcolor=black@0.9:boxborderw=35"
            f":x=(w-text_w)/2:y=h*0.82"
            f":enable='gt(t\\,{cta_start:.3f})'"
        )
        video_filters.append(
            f"drawtext=textfile={cta_file}"
            f":fontfile={font_file}:fontsize={cta_size}"
            f":fontcolor=yellow:borderw=4:bordercolor=black"
            f":x=(w-text_w)/2:y=h*0.82"
            f":alpha='if(gt(t\\,{cta_start:.3f})\\,if(eq(mod(floor((t-{cta_start:.3f})*2)\\,2)\\,0)\\,1\\,0.5)\\,0)'"
        )

    # ====== 音声フィルタ構築 ======
    extra_inputs: list[str] = []
    audio_segments: list[str] = []
    audio_mix_labels: list[str] = ["[0:a]"]
    audio_idx_counter = 1

    if bgm_path and Path(bgm_path).exists():
        extra_inputs += ["-i", bgm_path]
        bgm_input_idx = audio_idx_counter
        audio_idx_counter += 1
        fade_out_st = max(0.0, total_dur - bgm_fade)
        audio_segments.append(
            f"[{bgm_input_idx}:a]aloop=loop=-1:size=2e9,volume={bgm_volume},"
            f"afade=t=in:d={bgm_fade:.2f},"
            f"afade=t=out:d={bgm_fade:.2f}:st={fade_out_st:.3f},"
            f"atrim=duration={total_dur:.3f}[bgm]"
        )
        audio_mix_labels.append("[bgm]")

    if sfx_path and Path(sfx_path).exists() and sfx_timestamps_sec:
        extra_inputs += ["-i", sfx_path]
        sfx_input_idx = audio_idx_counter
        audio_idx_counter += 1
        for i, t in enumerate(sfx_timestamps_sec):
            delay_ms = max(0, int(t * 1000))
            audio_segments.append(
                f"[{sfx_input_idx}:a]adelay={delay_ms}|{delay_ms},volume={sfx_volume}[sfx{i}]"
            )
            audio_mix_labels.append(f"[sfx{i}]")

    # フィルタグラフ統合
    parts: list[str] = []
    has_video = bool(video_filters)
    has_audio_extra = len(audio_mix_labels) > 1

    if has_video:
        parts.append(f"[0:v]{','.join(video_filters)}[vout]")
    if has_audio_extra:
        parts.extend(audio_segments)
        parts.append(
            f"{''.join(audio_mix_labels)}amix=inputs={len(audio_mix_labels)}"
            f":duration=first:dropout_transition=0[aout]"
        )

    if not parts:
        # 何もしない -> コピー
        cmd = ["ffmpeg", "-y", "-i", input_video, "-c", "copy", output_video]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_video

    filter_complex = ";".join(parts)

    cmd = ["ffmpeg", "-y", "-i", input_video] + extra_inputs + [
        "-filter_complex", filter_complex,
    ]
    if has_video:
        cmd += ["-map", "[vout]"]
    else:
        cmd += ["-map", "0:v"]
    if has_audio_extra:
        cmd += ["-map", "[aout]"]
    else:
        cmd += ["-map", "0:a"]
    cmd += [
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-shortest",
        output_video,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg combined pipeline failed: {result.stderr}")
    return output_video
