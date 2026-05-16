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
