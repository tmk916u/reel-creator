import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.db_models import ScheduledPost, SocialConnection, Video
from app.services import publisher


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()


def _seed(db, status="scheduled", with_conn=True):
    vid = uuid.uuid4()
    db.add(Video(id=vid, file_url="u", storage_path="p"))
    post = ScheduledPost(
        video_id=vid, platform="youtube", status=status,
        title="t", description="d", hashtags="#a #b",
    )
    db.add(post)
    if with_conn:
        db.add(SocialConnection(platform="youtube", is_active=True, refresh_token="plain:rt"))
    db.commit()
    db.refresh(post)
    return post


def test_claim_only_once(db):
    post = _seed(db)
    assert publisher._claim(db, post.id) is True
    assert publisher._claim(db, post.id) is False  # 既に posting


def test_publish_youtube_success(db, monkeypatch, tmp_path):
    post = _seed(db)
    src = tmp_path / "source.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(publisher.storage, "source_path", lambda vid: src)
    captured = {}

    def fake_upload(refresh, path, **kw):
        captured.update(kw)
        captured["refresh"] = refresh
        return {"video_id": "YT123", "url": "https://youtu.be/YT123"}

    monkeypatch.setattr(publisher.youtube, "upload_video", fake_upload)

    result = publisher.publish_post(db, post.id)
    assert result.status == "posted"
    assert result.posted_url == "https://youtu.be/YT123"
    assert result.external_post_id == "YT123"
    assert result.posted_at is not None
    assert captured["refresh"] == "rt"  # 復号された refresh_token
    assert captured["title"] == "t"
    assert "#a #b" in captured["description"]


def test_publish_without_connection_fails(db, monkeypatch, tmp_path):
    post = _seed(db, with_conn=False)
    src = tmp_path / "source.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(publisher.storage, "source_path", lambda vid: src)
    result = publisher.publish_post(db, post.id)
    assert result.status == "failed"
    assert "連携" in (result.error_message or "")


def test_publish_missing_file_fails(db, monkeypatch, tmp_path):
    post = _seed(db)
    monkeypatch.setattr(publisher.storage, "source_path", lambda vid: tmp_path / "nope.mp4")
    result = publisher.publish_post(db, post.id)
    assert result.status == "failed"
    assert "動画ファイル" in (result.error_message or "")


def test_publish_posted_is_idempotent(db, monkeypatch):
    post = _seed(db, status="posted")
    called = {"n": 0}
    monkeypatch.setattr(publisher.youtube, "upload_video", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"video_id": "x", "url": "u"})
    result = publisher.publish_post(db, post.id)
    assert result.status == "posted"
    assert called["n"] == 0  # 再投稿していない


# --- Instagram (Phase 3) ---

def _seed_instagram(db, with_conn=True, with_env=False, monkeypatch=None):
    vid = uuid.uuid4()
    db.add(Video(id=vid, file_url="u", storage_path="p"))
    post = ScheduledPost(
        video_id=vid, platform="instagram", status="scheduled",
        caption="やせる食事の話", hashtags="#ダイエット #食事改善",
    )
    db.add(post)
    if with_conn:
        db.add(SocialConnection(
            platform="instagram", is_active=True,
            access_token="plain:page_token", external_account_id="IG123",
            account_name="my_account",
        ))
    db.commit()
    db.refresh(post)
    return post


def _setup_instagram_mocks(monkeypatch, tmp_path, *, https=True, mock_publish=True):
    src = tmp_path / "source.mp4"; src.write_bytes(b"x")
    monkeypatch.setattr(publisher.storage, "source_path", lambda vid: src)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://abc.ngrok.io" if https else "http://localhost:8000")
    if mock_publish:
        monkeypatch.setattr(
            publisher.instagram, "publish_to_instagram_with",
            lambda url, caption, **kw: {"success": True, "post_id": "IGPOST1", "message": "ok"},
        )
        monkeypatch.setattr(
            publisher.instagram, "fetch_permalink",
            lambda pid, **kw: "https://www.instagram.com/p/abc",
        )


def test_publish_instagram_with_connection(db, monkeypatch, tmp_path):
    post = _seed_instagram(db, with_conn=True)
    _setup_instagram_mocks(monkeypatch, tmp_path)
    captured = {}
    def fake(url, caption, *, access_token, ig_account_id):
        captured.update(url=url, caption=caption, access_token=access_token, ig_account_id=ig_account_id)
        return {"success": True, "post_id": "IGPOST1", "message": "ok"}
    monkeypatch.setattr(publisher.instagram, "publish_to_instagram_with", fake)

    result = publisher.publish_post(db, post.id)
    assert result.status == "posted"
    assert result.external_post_id == "IGPOST1"
    assert result.posted_url == "https://www.instagram.com/p/abc"
    assert captured["access_token"] == "page_token"  # 復号
    assert captured["ig_account_id"] == "IG123"
    assert "abc.ngrok.io" in captured["url"]
    assert "#ダイエット" in captured["caption"]


def test_publish_instagram_env_fallback(db, monkeypatch, tmp_path):
    post = _seed_instagram(db, with_conn=False)
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "env_token")
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "ENV_ACC")
    _setup_instagram_mocks(monkeypatch, tmp_path)
    captured = {}
    def fake(url, caption, *, access_token, ig_account_id):
        captured.update(access_token=access_token, ig_account_id=ig_account_id)
        return {"success": True, "post_id": "IGPOST2", "message": "ok"}
    monkeypatch.setattr(publisher.instagram, "publish_to_instagram_with", fake)

    result = publisher.publish_post(db, post.id)
    assert result.status == "posted"
    assert captured["access_token"] == "env_token"
    assert captured["ig_account_id"] == "ENV_ACC"


def test_publish_instagram_no_credentials_fails(db, monkeypatch, tmp_path):
    post = _seed_instagram(db, with_conn=False)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", raising=False)
    _setup_instagram_mocks(monkeypatch, tmp_path)
    result = publisher.publish_post(db, post.id)
    assert result.status == "failed"
    assert "連携" in (result.error_message or "")


def test_publish_instagram_requires_https_public_url(db, monkeypatch, tmp_path):
    post = _seed_instagram(db, with_conn=True)
    _setup_instagram_mocks(monkeypatch, tmp_path, https=False)
    result = publisher.publish_post(db, post.id)
    assert result.status == "failed"
    assert "HTTPS" in (result.error_message or "")


def test_publish_instagram_publish_error_recorded(db, monkeypatch, tmp_path):
    post = _seed_instagram(db, with_conn=True)
    _setup_instagram_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(
        publisher.instagram, "publish_to_instagram_with",
        lambda *a, **k: {"success": False, "post_id": None, "message": "API rate limit"},
    )
    result = publisher.publish_post(db, post.id)
    assert result.status == "failed"
    assert "rate limit" in (result.error_message or "")
