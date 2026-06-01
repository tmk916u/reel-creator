"""投稿機能（social-publishing）の CRUD・アップロード・メディア配信。

Phase 1: 動画アップロード / 投稿予約の作成・一覧・詳細・更新・削除。
実際の SNS 投稿（cron / publish）は Phase 2 以降。連携必須の検証も
OAuth 実装（Phase 2/3）と同時に有効化する。
"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import config
from app.db import get_db
from app.models.db_models import ScheduledPost, Video
from app.models.schemas import (
    CaptionSuggestionRequest,
    CaptionSuggestionResponse,
    PostCreate,
    PostOut,
    PostUpdate,
    ScheduledPostOut,
    UploadVideoResponse,
)
from app.services import publisher, storage
from app.services.captions_ai import LLMError, TranscribeError, suggest_captions
from app.services.hashtags import normalize_hashtags

router = APIRouter(prefix="/api/posts", tags=["posts"])

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")


def _media_url(video_id: uuid.UUID) -> str:
    return f"{PUBLIC_BASE_URL}/api/posts/media/{video_id}"


def _thumb_url(video_id: uuid.UUID) -> str:
    return f"{PUBLIC_BASE_URL}/api/posts/media/{video_id}/thumbnail"


@router.post("/upload", response_model=UploadVideoResponse)
def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = (file.filename or "").lower()
    if not name.endswith(".mp4") and file.content_type != "video/mp4":
        raise HTTPException(400, "MP4 のみアップロードできます")

    video_id = uuid.uuid4()
    max_bytes = config.MAX_FILE_SIZE_MB * 1024 * 1024
    try:
        src, _ = storage.save_source(str(video_id), file.file, max_bytes=max_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    duration = storage.probe_duration(src)
    thumb = storage.generate_thumbnail(str(video_id))
    thumbnail_url = _thumb_url(video_id) if thumb else None

    video = Video(
        id=video_id,
        file_url=_media_url(video_id),
        storage_path=str(src),
        original_filename=file.filename,
        thumbnail_url=thumbnail_url,
        duration_seconds=duration,
    )
    db.add(video)
    db.commit()

    return UploadVideoResponse(
        video_id=video_id,
        file_url=_media_url(video_id),
        thumbnail_url=thumbnail_url,
        duration_seconds=duration,
        original_filename=file.filename,
    )


@router.post("", response_model=PostOut, status_code=201)
def create_post(payload: PostCreate, db: Session = Depends(get_db)):
    video = db.get(Video, payload.video_id)
    if video is None:
        raise HTTPException(404, "動画が見つかりません")

    existing = db.scalars(
        select(ScheduledPost).where(ScheduledPost.video_id == video.id)
    ).first()
    if existing is not None:
        raise HTTPException(409, "この動画には既に投稿予約があります")

    try:
        hashtags = normalize_hashtags(payload.hashtags)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if payload.theme is not None:
        video.theme = payload.theme
    if payload.memo is not None:
        video.memo = payload.memo

    if payload.post_to_instagram:
        db.add(ScheduledPost(
            video_id=video.id,
            platform="instagram",
            scheduled_at=payload.instagram_scheduled_at,
            status="scheduled",
            caption=payload.instagram_caption,
            hashtags=hashtags or None,
        ))
    if payload.post_to_youtube:
        db.add(ScheduledPost(
            video_id=video.id,
            platform="youtube",
            scheduled_at=payload.youtube_scheduled_at,
            status="scheduled",
            title=payload.youtube_title,
            description=payload.youtube_description,
            hashtags=hashtags or None,
            privacy_status=payload.privacy_status,
        ))

    db.commit()
    db.refresh(video)
    return video


@router.get("", response_model=list[PostOut])
def list_posts(db: Session = Depends(get_db)):
    videos = db.scalars(
        select(Video).options(selectinload(Video.posts)).order_by(Video.created_at.desc())
    ).all()
    return list(videos)


@router.get("/media/{video_id}")
def serve_media(video_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Video, video_id) is None:
        raise HTTPException(404, "File not found")
    path = storage.source_path(str(video_id))
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(path), media_type="video/mp4")


@router.get("/media/{video_id}/thumbnail")
def serve_thumbnail(video_id: uuid.UUID, db: Session = Depends(get_db)):
    path = storage.thumbnail_path(str(video_id))
    if not path.exists():
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/{video_id}", response_model=PostOut)
def get_post(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "投稿が見つかりません")
    return video


@router.patch("/{video_id}", response_model=PostOut)
def update_post(video_id: uuid.UUID, payload: PostUpdate, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "投稿が見つかりません")
    if any(p.status == "posted" for p in video.posts):
        raise HTTPException(409, "投稿済みのため編集できません。複製して編集してください")

    hashtags = None
    if payload.hashtags is not None:
        try:
            hashtags = normalize_hashtags(payload.hashtags)
        except ValueError as e:
            raise HTTPException(422, str(e))

    if payload.theme is not None:
        video.theme = payload.theme
    if payload.memo is not None:
        video.memo = payload.memo

    posts = {p.platform: p for p in video.posts}
    ig = posts.get("instagram")
    if ig is not None:
        if payload.instagram_caption is not None:
            ig.caption = payload.instagram_caption
        if payload.instagram_scheduled_at is not None:
            ig.scheduled_at = payload.instagram_scheduled_at
        if hashtags is not None:
            ig.hashtags = hashtags or None
    yt = posts.get("youtube")
    if yt is not None:
        if payload.youtube_title is not None:
            yt.title = payload.youtube_title
        if payload.youtube_description is not None:
            yt.description = payload.youtube_description
        if payload.youtube_scheduled_at is not None:
            yt.scheduled_at = payload.youtube_scheduled_at
        if payload.privacy_status is not None:
            yt.privacy_status = payload.privacy_status
        if hashtags is not None:
            yt.hashtags = hashtags or None

    db.commit()
    db.refresh(video)
    return video


@router.delete("/{video_id}", status_code=204)
def delete_post(video_id: uuid.UUID, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "投稿が見つかりません")
    db.delete(video)
    db.commit()
    storage.delete_video_files(str(video_id))


@router.post("/{post_id}/publish_now", response_model=ScheduledPostOut)
def publish_now(post_id: uuid.UUID, db: Session = Depends(get_db)):
    """対象の scheduled_post を即時投稿する（posted は再投稿しない）。"""
    try:
        return publisher.publish_post(db, post_id)
    except LookupError:
        raise HTTPException(404, "投稿が見つかりません")


@router.post("/{post_id}/retry", response_model=ScheduledPostOut)
def retry_post(post_id: uuid.UUID, db: Session = Depends(get_db)):
    post = db.get(ScheduledPost, post_id)
    if post is None:
        raise HTTPException(404, "投稿が見つかりません")
    if post.status != "failed":
        raise HTTPException(409, "失敗した投稿のみリトライできます")
    post.retry_count += 1
    db.commit()
    return publisher.publish_post(db, post_id)


@router.post("/{video_id}/suggest", response_model=CaptionSuggestionResponse)
def suggest_captions_endpoint(
    video_id: uuid.UUID,
    payload: CaptionSuggestionRequest = CaptionSuggestionRequest(),
    db: Session = Depends(get_db),
):
    """書き起こし + LLM で投稿用テキスト一式を生成する（add-ai-caption-suggest）。"""
    if db.get(Video, video_id) is None:
        raise HTTPException(404, "動画が見つかりません")
    try:
        result = suggest_captions(str(video_id), theme=payload.theme)
    except TranscribeError as e:
        raise HTTPException(422, f"書き起こしに失敗しました: {e}")
    except LLMError as e:
        raise HTTPException(502, f"AI 生成に失敗しました: {e}")
    return CaptionSuggestionResponse(
        instagram_caption=result.instagram_caption,
        youtube_title=result.youtube_title,
        youtube_description=result.youtube_description,
        hashtags=result.hashtags,
        cover_text_candidates=result.cover_text_candidates,
    )
