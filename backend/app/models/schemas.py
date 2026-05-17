# backend/app/models/schemas.py
from pydantic import BaseModel
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FontSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class SubtitlePosition(str, Enum):
    BOTTOM = "bottom"
    CENTER = "center"


class SubtitleColor(str, Enum):
    WHITE = "white"
    YELLOW = "yellow"


class EditedSegment(BaseModel):
    start: float
    end: float
    text: str


class ProcessRequest(BaseModel):
    silence_threshold: float = -30.0  # dB
    min_silence_duration: float = 0.3  # seconds
    voice_padding: float = 0.04  # 有音区間の前後に残すバッファ秒（小さいほど詰まる）
    tempo_max_pause: float = 0.6  # 句読点後この秒数を超える間を縮める対象に
    tempo_target_pause: float = 0.3  # 縮めた後に残す間（秒）
    word_gap_max: float = 0.25  # word 間ギャップがこの秒数を超えると圧縮対象に
    word_gap_target: float = 0.10  # 圧縮後に残す word 間ギャップ（秒）
    max_word_duration: float = 1.0  # word.end-start がこの秒数を超えると中央部を削除候補に
    # ReazonSpeech の subword 単一点 timestamp 推定により、発話間の長い沈黙が word
    # に取り込まれる現象への対策。例:「首」word が 4.24秒続く → 中央 3.84秒を削除。
    micro_silence_min_duration: float = 0.10  # 音響的な微小無音検出の閾値(秒)。
    # ReazonSpeech の word 内に埋もれる「整骨院の前のちょっとした間」のような短い無音を
    # ffmpeg silencedetect で別途検出し、Silero VAD silences と union を取る。
    # 0 にすると無効。
    subtitle_max_chars: int = 12  # 1字幕の最大文字数（リール用は短め推奨）
    trim_leading_silence: bool = False  # 互換のため残す（現状は no-op、VAD が冒頭無音を自動削除）
    topic_style: str = "default"  # トピックテロップのスタイル: default | sleek | clean
    enable_sfx: bool = False  # 効果音をカット境界に挿入(data/sfx/cut.mp3 を配置していれば動作)
    enable_subtitles: bool = False
    enable_jump_cut: bool = False
    enable_buzz_mode: bool = False  # 冒頭フック + モーション字幕
    transcript_prompt: str = ""  # Whisperに渡す文脈（テーマ・専門用語）
    font_size: FontSize = FontSize.MEDIUM
    subtitle_position: SubtitlePosition = SubtitlePosition.BOTTOM
    subtitle_color: SubtitleColor = SubtitleColor.WHITE
    edited_segments: list[EditedSegment] | None = None  # プレビュー編集後の字幕


class TranscribeRequest(BaseModel):
    transcript_prompt: str = ""


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    job_id: str
    segments: list[TranscriptSegment]


class CaptionsResponse(BaseModel):
    job_id: str
    tiktok_caption: str
    instagram_caption: str
    hashtags: str


class WriteCaptionsRequest(BaseModel):
    sheet_row: int
    ig_caption: str
    tiktok_caption: str
    hashtags: str


class BuzzScoreDetail(BaseModel):
    hook: int = 0
    clarity: int = 0
    density: int = 0
    structure: int = 0
    cta: int = 0
    pace: int = 0
    searchability: int = 0
    length_fit: int = 0


class BuzzScoreResponse(BaseModel):
    job_id: str
    overall: float
    scores: BuzzScoreDetail
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    duration: float
    file_size: int


class ProcessResponse(BaseModel):
    job_id: str
    status: JobStatus


class ProgressEvent(BaseModel):
    job_id: str
    status: JobStatus
    stage: str
    progress: int  # 0-100
    message: str


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    original_duration: float
    processed_duration: float
    silence_removed: float


# --- SNS Publish ---

class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class PublishRequest(BaseModel):
    sheet_row: int
    platforms: list[Platform]


class PublishResult(BaseModel):
    platform: str
    success: bool
    message: str
    post_id: str | None = None


class PublishResponse(BaseModel):
    job_id: str
    results: list[PublishResult]
