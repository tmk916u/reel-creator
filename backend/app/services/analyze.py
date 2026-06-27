"""入力動画を解析して「おまかせ」設定を推薦する。

発話量(Silero VAD の speech 比率)と向き(横/縦)から、動画の性質を判定して
ProcessRequest 相当の推奨設定を返す。これにより「動画を入れるだけ」で
種類に合った仕上げ(トーク主体=無音削除+字幕 / 映像主体=全長キープ+色味)に
自動で寄せられる。

recommend_settings は純粋関数(I/O なし)なのでユニットテスト可能。
"""
from __future__ import annotations

import logging

from app.services.ffmpeg import get_video_duration
from app.services.reframe import probe_dimensions
from app.services.vad import detect_silence_silero

logger = logging.getLogger(__name__)

VERTICAL_AR = 9 / 16  # これ以下(縦長)はオートリフレーム不要


def recommend_settings(
    speech_ratio: float, width: int, height: int, duration: float
) -> dict:
    """発話比率・解像度・尺から推奨設定を組み立てる(純粋関数)。

    Returns: {profile, label, reason, speech_ratio, orientation, settings}
    settings は ProcessRequest のフィールド上書き(部分)。
    """
    is_vertical = (width / height) <= (VERTICAL_AR + 0.02) if height else True
    reframe = not is_vertical
    pct = round(speech_ratio * 100)

    if speech_ratio >= 0.45:
        profile = "talk"
        label = "トーク主体"
        reason = (
            f"発話が約{pct}%。無音削除とジャンプカットで引き締め、"
            f"キネティック字幕とシネマ色味で仕上げます。"
        )
        settings = {
            "enable_subtitles": True,
            "enable_jump_cut": True,
            "enable_buzz_mode": True,
            "subtitle_motion": "pop",
            "color_grade": "cinematic",
        }
    elif speech_ratio <= 0.18:
        profile = "visual"
        label = "映像・デモ主体"
        reason = (
            f"発話が約{pct}%と少なめ。全長を保って色味で仕上げ、"
            f"誤字幕(prompt echo)を避けるため字幕は控えます。"
        )
        settings = {
            "enable_subtitles": False,
            "enable_jump_cut": False,
            "enable_buzz_mode": False,
            "color_grade": "cinematic",
            "min_silence_duration": 999.0,  # 実質 無音削除オフ(全長キープ)
            "silence_threshold": -60.0,
        }
    else:
        profile = "mixed"
        label = "ミックス"
        reason = (
            f"発話が約{pct}%。無音は軽く削り、字幕(フェード)と"
            f"ミニマル色味で自然に仕上げます。"
        )
        settings = {
            "enable_subtitles": True,
            "enable_jump_cut": True,
            "enable_buzz_mode": True,
            "subtitle_motion": "fade",
            "color_grade": "minimal",
        }

    settings["enable_auto_reframe"] = reframe
    return {
        "profile": profile,
        "label": label,
        "reason": reason,
        "speech_ratio": round(speech_ratio, 3),
        "orientation": "vertical" if is_vertical else "landscape",
        "settings": settings,
    }


def analyze_video(input_path: str, audio_path: str) -> dict:
    """動画/音声を解析して推奨設定を返す。VAD/probe 失敗時は安全側(mixed相当)。"""
    duration = get_video_duration(input_path)
    dims = probe_dimensions(input_path) or (1080, 1920)
    width, height = dims

    silences = detect_silence_silero(audio_path, min_silence_duration=0.4) or []
    silence_total = sum(max(0.0, s["end"] - s["start"]) for s in silences)
    speech_ratio = max(0.0, (duration - silence_total) / duration) if duration > 0 else 0.3

    logger.info(
        "analyze: %dx%d, %.1fs, speech_ratio=%.2f", width, height, duration, speech_ratio
    )
    return recommend_settings(speech_ratio, width, height, duration)
