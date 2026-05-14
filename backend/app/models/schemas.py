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


class ProcessRequest(BaseModel):
    silence_threshold: float = -30.0  # dB
    min_silence_duration: float = 0.5  # seconds
    enable_subtitles: bool = False
    enable_jump_cut: bool = False
    font_size: FontSize = FontSize.MEDIUM
    subtitle_position: SubtitlePosition = SubtitlePosition.BOTTOM
    subtitle_color: SubtitleColor = SubtitleColor.WHITE


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
