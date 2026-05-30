"""予約投稿の実行（design D6/D7）。

二重投稿防止のため、投稿実行前に atomic な条件付き UPDATE で
`posting` を claim する（更新行数 1 のときのみ実投稿）。
Phase 2 は YouTube のみ。Instagram は Phase 3。
"""
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.db_models import ScheduledPost, SocialConnection
from app.services import crypto, instagram, storage, youtube

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_connection(db: Session, platform: str) -> SocialConnection | None:
    return db.scalars(
        select(SocialConnection).where(
            SocialConnection.platform == platform,
            SocialConnection.is_active.is_(True),
        )
    ).first()


def _claim(db: Session, post_id) -> bool:
    """scheduled/failed → posting に atomic 遷移。成功時のみ True。"""
    res = db.execute(
        update(ScheduledPost)
        .where(
            ScheduledPost.id == post_id,
            ScheduledPost.status.in_(["scheduled", "failed"]),
        )
        .values(status="posting", updated_at=_now())
    )
    db.commit()
    return res.rowcount == 1


def publish_post(db: Session, post_id) -> ScheduledPost:
    """単一の scheduled_post を投稿する。冪等（posted は再投稿しない）。"""
    post = db.get(ScheduledPost, post_id)
    if post is None:
        raise LookupError("scheduled_post not found")

    if post.status == "posted":
        return post  # 再投稿しない

    if not _claim(db, post_id):
        db.refresh(post)
        return post  # 既に他で処理中 / 対象外

    db.refresh(post)
    try:
        result = _dispatch(db, post)
        post.status = "posted"
        post.posted_url = result["url"]
        post.external_post_id = result["video_id"]
        post.posted_at = _now()
        post.error_message = None
    except Exception as e:
        logger.warning("投稿失敗 post=%s platform=%s: %s", post_id, post.platform, e)
        post.status = "failed"
        post.error_message = str(e)[:2000]

    db.commit()
    db.refresh(post)
    return post


def run_due_posts(db: Session, limit: int = 20) -> int:
    """予約時刻が到来した scheduled を投稿する（Phase 4 の cron から呼ぶ）。"""
    due = db.scalars(
        select(ScheduledPost)
        .where(
            ScheduledPost.status == "scheduled",
            ScheduledPost.scheduled_at.is_not(None),
            ScheduledPost.scheduled_at <= _now(),
        )
        .limit(limit)
    ).all()
    count = 0
    for post in due:
        publish_post(db, post.id)
        count += 1
    return count


def _dispatch(db: Session, post: ScheduledPost) -> dict:
    if post.platform == "youtube":
        return _publish_youtube(db, post)
    if post.platform == "instagram":
        return _publish_instagram(db, post)
    raise RuntimeError(f"未対応プラットフォーム: {post.platform}")


def _publish_youtube(db: Session, post: ScheduledPost) -> dict:
    conn = get_active_connection(db, "youtube")
    if conn is None or not conn.refresh_token:
        raise RuntimeError("YouTube 連携が未設定です")

    refresh_token = crypto.decrypt(conn.refresh_token)
    src = storage.source_path(str(post.video_id))
    if not src.exists():
        raise RuntimeError("動画ファイルが見つかりません")

    description = post.description or ""
    if post.hashtags:
        description = f"{description}\n\n{post.hashtags}".strip()
    tags = [h.lstrip("#") for h in post.hashtags.split()] if post.hashtags else None

    return youtube.upload_video(
        refresh_token,
        str(src),
        title=post.title or "",
        description=description,
        privacy_status=post.privacy_status or "public",
        tags=tags,
    )


def _publish_instagram(db: Session, post: ScheduledPost) -> dict:
    """連携あれば優先。なければ env 変数（既存運用）にフォールバック。"""
    conn = get_active_connection(db, "instagram")
    if conn and conn.access_token and conn.external_account_id:
        access_token = crypto.decrypt(conn.access_token)
        ig_account_id = conn.external_account_id
    else:
        access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
        ig_account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        if not (access_token and ig_account_id):
            raise RuntimeError("Instagram 連携が未設定です")

    public_base = os.environ.get("PUBLIC_BASE_URL", "")
    if not public_base.startswith("https://"):
        raise RuntimeError(
            "Instagram 投稿には HTTPS の PUBLIC_BASE_URL が必要です（ngrok 等で公開してください）"
        )

    # 動画ファイルの存在確認（IG は URL 経由で取得するが、URL の先が空だと失敗するため）
    if not storage.source_path(str(post.video_id)).exists():
        raise RuntimeError("動画ファイルが見つかりません")

    video_url = f"{public_base}/api/posts/media/{post.video_id}"
    caption = post.caption or ""
    if post.hashtags:
        caption = f"{caption}\n\n{post.hashtags}".strip()

    result = instagram.publish_to_instagram_with(
        video_url, caption, access_token=access_token, ig_account_id=ig_account_id
    )
    if not result["success"]:
        raise RuntimeError(result["message"])

    post_id = result["post_id"]
    permalink = instagram.fetch_permalink(post_id, access_token=access_token)
    return {
        "video_id": post_id,
        "url": permalink or f"https://www.instagram.com/p/{post_id}",
    }
