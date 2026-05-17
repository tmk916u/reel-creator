"""アプリ全体のパラメータ集中管理。

環境変数でオーバーライド可能。デフォルト値は経験的にバランスを取った値。
"""
import os


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


# ===== 動画アップロード =====
MAX_FILE_SIZE_MB = _env_int("MAX_FILE_SIZE_MB", 1024)
MAX_DURATION_SEC = _env_int("MAX_DURATION_SEC", 300)

# ===== ジョブクリーンアップ =====
CLEANUP_INTERVAL_SEC = _env_int("CLEANUP_INTERVAL_SEC", 300)
JOB_MAX_AGE_SEC = _env_int("JOB_MAX_AGE_SEC", 86400)  # 24h

# ===== Whisper / 文字起こし =====
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium")
DEFAULT_TRANSCRIPT_PROMPT = (
    "日本語で話している動画の文字起こしです。"
)

# ===== 字幕表示 =====
SUBTITLE_MAX_CHARS = _env_int("SUBTITLE_MAX_CHARS", 18)
SUBTITLE_MAX_GAP = _env_float("SUBTITLE_MAX_GAP", 0.6)
SUBTITLE_LEAD_TIME = _env_float("SUBTITLE_LEAD_TIME", 0.12)
SUBTITLE_TAIL_TIME = _env_float("SUBTITLE_TAIL_TIME", 0.15)

# ===== 無音検出・カット =====
SILENCE_THRESHOLD_DB = _env_float("SILENCE_THRESHOLD_DB", -30.0)
MIN_SILENCE_DURATION_SEC = _env_float("MIN_SILENCE_DURATION_SEC", 0.5)
VOICE_PADDING_SEC = _env_float("VOICE_PADDING_SEC", 0.05)
MIN_CUT_LENGTH_SEC = _env_float("MIN_CUT_LENGTH_SEC", 0.08)
AUDIO_FADE_SEC = _env_float("AUDIO_FADE_SEC", 0.04)

# ===== ジャンプカット =====
TEMPO_MAX_PAUSE_SEC = _env_float("TEMPO_MAX_PAUSE_SEC", 0.6)
TEMPO_TARGET_PAUSE_SEC = _env_float("TEMPO_TARGET_PAUSE_SEC", 0.3)

# ===== バズモード演出 =====
HOOK_DURATION_SEC = _env_float("HOOK_DURATION_SEC", 3.0)
HOOK_FONT_SIZE = _env_int("HOOK_FONT_SIZE", 80)
CTA_DURATION_SEC = _env_float("CTA_DURATION_SEC", 3.0)
CTA_FONT_SIZE = _env_int("CTA_FONT_SIZE", 80)  # 顔を隠さない控えめサイズ
CTA_TEXT = os.getenv("CTA_TEXT", "▼ 保存して見返してね")
TOPIC_NUMBER_SIZE = _env_int("TOPIC_NUMBER_SIZE", 150)
TOPIC_LABEL_SIZE = _env_int("TOPIC_LABEL_SIZE", 60)
TOPIC_MAX_COUNT = _env_int("TOPIC_MAX_COUNT", 4)

# ===== 音響 =====
BGM_VOLUME = _env_float("BGM_VOLUME", 0.12)
BGM_FADE_SEC = _env_float("BGM_FADE_SEC", 1.5)
SFX_VOLUME = _env_float("SFX_VOLUME", 0.15)
SFX_MAX_COUNT = _env_int("SFX_MAX_COUNT", 20)
SFX_MIN_INTERVAL_SEC = _env_float("SFX_MIN_INTERVAL_SEC", 0.5)

# ===== フォント =====
FONT_SIZE_PX = {
    "small": _env_int("FONT_SIZE_SMALL_PX", 16),
    "medium": _env_int("FONT_SIZE_MEDIUM_PX", 22),
    "large": _env_int("FONT_SIZE_LARGE_PX", 30),
}
SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "Noto Sans CJK JP")
NOTO_FONT_PATH = os.getenv(
    "NOTO_FONT_PATH",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
)

# ===== データディレクトリ =====
BGM_DIR = os.getenv("BGM_DIR", "/app/app/data/bgm")
SFX_DIR = os.getenv("SFX_DIR", "/app/app/data/sfx")
CORRECTIONS_PATH = os.getenv(
    "CORRECTIONS_PATH",
    "/app/app/data/jp_corrections.txt",
)
FILLERS_PATH = os.getenv(
    "FILLERS_PATH",
    "/app/app/data/jp_fillers.txt",
)
