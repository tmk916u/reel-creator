# backend/app/models/schemas.py
import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


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


class ColorGrade(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    CINEMATIC = "cinematic"
    MONOCHROME = "monochrome"
    POP = "pop"


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
    editor_mode: str = "rule_based"  # "rule_based" (既存、 削除候補ボトムアップ)
                                     # | "director" (LLM が残す区間をトップダウン設計)
    director_target_min: float = 50.0  # director mode の出力尺下限 (秒)
    director_target_max: float = 80.0  # director mode の出力尺上限 (秒)
    transcript_prompt: str = ""  # Whisperに渡す文脈（テーマ・専門用語）
    font_size: FontSize = FontSize.MEDIUM
    subtitle_position: SubtitlePosition = SubtitlePosition.BOTTOM
    subtitle_color: SubtitleColor = SubtitleColor.WHITE
    subtitle_motion: str = "pop"  # キネティック字幕: none|karaoke|fade|pop (バズモード/ASS時のみ)
    color_grade: ColorGrade = ColorGrade.NONE  # テイスト別カラーグレード(LUT)。none で従来同一
    enable_auto_reframe: bool = False  # 被写体追従オートリフレーム(横→9:16でも中心維持)
    reframe_sample_fps: float = 3.0  # リフレーム検出のフレームサンプリングfps
    reframe_smoothing: float = 0.85  # カット間の中心EMA平滑(0..1, 大きいほど滑らか)
    reframe_padding: float = 0.15  # 被写体周りの余白(将来用)
    edited_segments: list[EditedSegment] | None = None  # プレビュー編集後の字幕


class TranscribeRequest(BaseModel):
    transcript_prompt: str = ""


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    suspicious: bool = False  # 誤認識候補なら True (frontend で赤字ハイライト)


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


# --- 投稿機能 (social-publishing) ---

PostPlatform = Literal["instagram", "youtube"]
PrivacyStatus = Literal["public", "private", "unlisted"]


class UploadVideoResponse(BaseModel):
    video_id: uuid.UUID
    file_url: str
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    original_filename: str | None = None


class PostCreate(BaseModel):
    video_id: uuid.UUID
    theme: str | None = None
    memo: str | None = None
    hashtags: str | None = None

    post_to_instagram: bool = False
    post_to_youtube: bool = False

    instagram_caption: str | None = None
    instagram_scheduled_at: datetime | None = None

    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_scheduled_at: datetime | None = None
    privacy_status: PrivacyStatus = "public"

    @model_validator(mode="after")
    def _validate(self):
        if not self.post_to_instagram and not self.post_to_youtube:
            raise ValueError("Instagram と YouTube のどちらか一方は ON にしてください")

        if self.post_to_instagram:
            if not (self.instagram_caption and self.instagram_caption.strip()):
                raise ValueError("Instagram キャプションは必須です")
            if self.instagram_scheduled_at is None:
                raise ValueError("Instagram 投稿予定日時は必須です")

        if self.post_to_youtube:
            if not (self.youtube_title and self.youtube_title.strip()):
                raise ValueError("YouTube タイトルは必須です")
            if not (self.youtube_description and self.youtube_description.strip()):
                raise ValueError("YouTube 説明文は必須です")
            if self.youtube_scheduled_at is None:
                raise ValueError("YouTube 投稿予定日時は必須です")

        return self


class PostUpdate(BaseModel):
    theme: str | None = None
    memo: str | None = None
    hashtags: str | None = None
    instagram_caption: str | None = None
    instagram_scheduled_at: datetime | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    youtube_scheduled_at: datetime | None = None
    privacy_status: PrivacyStatus | None = None


class ScheduledPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    scheduled_at: datetime | None = None
    status: str
    caption: str | None = None
    title: str | None = None
    description: str | None = None
    hashtags: str | None = None
    privacy_status: str | None = None
    posted_url: str | None = None
    external_post_id: str | None = None
    error_message: str | None = None
    retry_count: int
    posted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PostOut(BaseModel):
    """動画 1 本 + 媒体別 scheduled_posts の集約。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_url: str
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    aspect_ratio: str | None = None
    theme: str | None = None
    memo: str | None = None
    original_filename: str | None = None
    created_at: datetime
    updated_at: datetime
    posts: list[ScheduledPostOut] = []


class ConnectionOut(BaseModel):
    """SNS 連携状態（トークンは含めない）。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    account_name: str | None = None
    external_account_id: str | None = None
    is_active: bool
    token_expires_at: datetime | None = None
    created_at: datetime


# --- AI キャプション生成 (add-ai-caption-suggest) ---

class CaptionSuggestionRequest(BaseModel):
    theme: str | None = None


class CaptionSuggestionResponse(BaseModel):
    instagram_caption: str
    youtube_title: str
    youtube_description: str
    hashtags: list[str] = []
    cover_text_candidates: list[str] = []


# --- アカウント文脈プロファイル (account-context-profile) ---

class AccountProfileIn(BaseModel):
    """プロファイル更新リクエスト。全フィールド任意。"""
    niche: str | None = None
    target_audience: str | None = None
    tone: str | None = None
    goals: str | None = None
    hashtags: str | None = None
    ng_words: str | None = None
    notes: str | None = None


class AccountProfileOut(AccountProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    updated_at: datetime
