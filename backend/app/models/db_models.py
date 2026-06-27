"""投稿機能（social-publishing）の DB モデル。

要件定義書 §5 のデータモデルに準拠。uuid PK / timezone 付き timestamp。
Uuid / DateTime(timezone=True) は Postgres とテスト用 SQLite の両方で動く。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(512))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    aspect_ratio: Mapped[str | None] = mapped_column(String(32))
    theme: Mapped[str | None] = mapped_column(String(512))
    memo: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    posts: Mapped[list["ScheduledPost"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="ScheduledPost.platform",
    )


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # instagram / youtube
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", index=True)
    caption: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[str | None] = mapped_column(Text)
    privacy_status: Mapped[str | None] = mapped_column(String(32))  # public / private / unlisted
    posted_url: Mapped[str | None] = mapped_column(Text)
    external_post_id: Mapped[str | None] = mapped_column(String(256))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    video: Mapped["Video"] = relationship(back_populates="posts")


class AccountProfile(Base):
    """アカウント文脈プロファイル（account-context-profile）。

    アカウントの性質（ジャンル/ターゲット/トーン/目的）を 1 件保持し、
    AI キャプション生成のシステムプロンプトに注入する。MVP は単一プロファイル
    （is_active=True を get-or-create）で運用する。
    """
    __tablename__ = "account_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    niche: Mapped[str | None] = mapped_column(Text)            # ジャンル/専門領域
    target_audience: Mapped[str | None] = mapped_column(Text)  # ターゲット視聴者
    tone: Mapped[str | None] = mapped_column(Text)             # トーン/語り口
    goals: Mapped[str | None] = mapped_column(Text)            # 運用目的（集客/権威性 等）
    hashtags: Mapped[str | None] = mapped_column(Text)         # 定番ハッシュタグ
    ng_words: Mapped[str | None] = mapped_column(Text)         # 避ける語/表現
    notes: Mapped[str | None] = mapped_column(Text)            # 自由メモ/例文
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SocialConnection(Base):
    __tablename__ = "social_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # instagram / youtube
    account_name: Mapped[str | None] = mapped_column(String(256))
    external_account_id: Mapped[str | None] = mapped_column(String(256))
    access_token: Mapped[str | None] = mapped_column(Text)  # 暗号化保存（Phase 2+）
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
