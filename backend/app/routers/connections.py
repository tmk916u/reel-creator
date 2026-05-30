"""SNS アカウント連携（OAuth）。Phase 2: YouTube (Google OAuth)。

連携トークンは social_connections に暗号化保存する（design D5）。
ブラウザ起点のフローのため、コールバック後はフロントの連携画面へ戻す。
"""
import os
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.db_models import SocialConnection
from app.models.schemas import ConnectionOut
from app.services import crypto, instagram, youtube

router = APIRouter(prefix="/api/connections", tags=["connections"])

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3002")
_pending_states: set[str] = set()


def _result_redirect(query: str) -> RedirectResponse:
    return RedirectResponse(f"{FRONTEND_BASE_URL}/post/connections?{query}", status_code=303)


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(SocialConnection).order_by(SocialConnection.platform)
    ).all()
    return list(rows)


@router.get("/youtube/start")
def youtube_start():
    try:
        state = secrets.token_urlsafe(16)
        _pending_states.add(state)
        url = youtube.build_auth_url(state)
    except RuntimeError:
        return _result_redirect("youtube_error=not_configured")
    return RedirectResponse(url, status_code=307)


@router.get("/youtube/callback")
def youtube_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if error:
        return _result_redirect(f"youtube_error={error}")
    if not code:
        return _result_redirect("youtube_error=missing_code")

    _pending_states.discard(state or "")

    try:
        info = youtube.exchange_code(code)
    except Exception:
        return _result_redirect("youtube_error=exchange_failed")

    conn = db.scalars(
        select(SocialConnection).where(SocialConnection.platform == "youtube")
    ).first()
    if conn is None:
        conn = SocialConnection(platform="youtube")
        db.add(conn)

    conn.account_name = info["account_name"]
    conn.external_account_id = info["external_account_id"]
    if info["refresh_token"]:  # 再同意で None のことがあるので既存を温存
        conn.refresh_token = crypto.encrypt(info["refresh_token"])
    conn.access_token = crypto.encrypt(info["access_token"])
    conn.token_expires_at = info["token_expires_at"]
    conn.is_active = True
    db.commit()

    return _result_redirect("connected=youtube")


@router.get("/meta/start")
def meta_start():
    try:
        state = secrets.token_urlsafe(16)
        _pending_states.add(state)
        url = instagram.build_meta_auth_url(state)
    except RuntimeError:
        return _result_redirect("instagram_error=not_configured")
    return RedirectResponse(url, status_code=307)


@router.get("/meta/callback")
def meta_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if error:
        return _result_redirect(f"instagram_error={error}")
    if not code:
        return _result_redirect("instagram_error=missing_code")

    _pending_states.discard(state or "")

    try:
        info = instagram.exchange_meta_code(code)
    except Exception:
        return _result_redirect("instagram_error=exchange_failed")

    conn = db.scalars(
        select(SocialConnection).where(SocialConnection.platform == "instagram")
    ).first()
    if conn is None:
        conn = SocialConnection(platform="instagram")
        db.add(conn)

    conn.account_name = info["account_name"]
    conn.external_account_id = info["external_account_id"]
    conn.access_token = crypto.encrypt(info["access_token"])
    if info.get("refresh_token"):
        conn.refresh_token = crypto.encrypt(info["refresh_token"])
    conn.token_expires_at = info.get("token_expires_at")
    conn.is_active = True
    db.commit()

    return _result_redirect("connected=instagram")


@router.delete("/{conn_id}", status_code=204)
def disconnect(conn_id: uuid.UUID, db: Session = Depends(get_db)):
    conn = db.get(SocialConnection, conn_id)
    if conn is None:
        raise HTTPException(404, "連携が見つかりません")
    db.delete(conn)
    db.commit()
