import uuid
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models.db_models import ScheduledPost, Video
from app.routers.posts import router as posts_router


@dataclass
class Ctx:
    client: TestClient
    Session: sessionmaker


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    from app.services import storage
    monkeypatch.setattr(storage, "MEDIA_DIR", tmp_path)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = FastAPI()
    app.include_router(posts_router)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return Ctx(client=TestClient(app), Session=TestingSession)


def _make_video(ctx: Ctx) -> str:
    vid = uuid.uuid4()
    with ctx.Session() as db:
        db.add(Video(
            id=vid,
            file_url=f"http://x/api/posts/media/{vid}",
            storage_path=f"/media/{vid}/source.mp4",
            original_filename="clip.mp4",
        ))
        db.commit()
    return str(vid)


# --- upload ---

def test_upload_rejects_non_mp4(ctx):
    resp = ctx.client.post(
        "/api/posts/upload",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_mp4_creates_video(ctx):
    resp = ctx.client.post(
        "/api/posts/upload",
        files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"]
    with ctx.Session() as db:
        assert db.get(Video, uuid.UUID(body["video_id"])) is not None


# --- create validation (D8) ---

def test_create_both_off_rejected(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "post_to_instagram": False,
        "post_to_youtube": False,
    })
    assert resp.status_code == 422


def test_create_instagram_requires_caption(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "post_to_instagram": True,
        "instagram_scheduled_at": "2026-06-01T12:00:00+09:00",
    })
    assert resp.status_code == 422


def test_create_instagram_requires_schedule(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "post_to_instagram": True,
        "instagram_caption": "やせる食事の話",
    })
    assert resp.status_code == 422


def test_create_youtube_requires_fields(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "post_to_youtube": True,
        "youtube_title": "タイトル",
        "youtube_scheduled_at": "2026-06-01T12:00:00+09:00",
    })
    assert resp.status_code == 422  # description 欠落


def test_create_valid_makes_two_posts(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "theme": "ダイエット",
        "hashtags": "ダイエット 食事改善",
        "post_to_instagram": True,
        "instagram_caption": "やせる食事の話",
        "instagram_scheduled_at": "2026-06-01T12:00:00+09:00",
        "post_to_youtube": True,
        "youtube_title": "やせる食事",
        "youtube_description": "説明文",
        "youtube_scheduled_at": "2026-06-01T12:05:00+09:00",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["theme"] == "ダイエット"
    platforms = sorted(p["platform"] for p in body["posts"])
    assert platforms == ["instagram", "youtube"]
    assert all(p["status"] == "scheduled" for p in body["posts"])
    ig = next(p for p in body["posts"] if p["platform"] == "instagram")
    assert ig["hashtags"] == "#ダイエット #食事改善"


def test_create_hashtags_over_limit_rejected(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.post("/api/posts", json={
        "video_id": vid,
        "hashtags": "a b c d e f",
        "post_to_instagram": True,
        "instagram_caption": "cap",
        "instagram_scheduled_at": "2026-06-01T12:00:00+09:00",
    })
    assert resp.status_code == 422


def test_create_duplicate_rejected(ctx):
    vid = _make_video(ctx)
    payload = {
        "video_id": vid,
        "post_to_youtube": True,
        "youtube_title": "t",
        "youtube_description": "d",
        "youtube_scheduled_at": "2026-06-01T12:05:00+09:00",
    }
    assert ctx.client.post("/api/posts", json=payload).status_code == 201
    assert ctx.client.post("/api/posts", json=payload).status_code == 409


def test_create_missing_video_404(ctx):
    resp = ctx.client.post("/api/posts", json={
        "video_id": str(uuid.uuid4()),
        "post_to_youtube": True,
        "youtube_title": "t",
        "youtube_description": "d",
        "youtube_scheduled_at": "2026-06-01T12:05:00+09:00",
    })
    assert resp.status_code == 404


# --- list / detail ---

def test_list_and_detail(ctx):
    vid = _make_video(ctx)
    ctx.client.post("/api/posts", json={
        "video_id": vid,
        "post_to_youtube": True,
        "youtube_title": "t",
        "youtube_description": "d",
        "youtube_scheduled_at": "2026-06-01T12:05:00+09:00",
    })
    lst = ctx.client.get("/api/posts")
    assert lst.status_code == 200
    assert len(lst.json()) == 1

    detail = ctx.client.get(f"/api/posts/{vid}")
    assert detail.status_code == 200
    assert detail.json()["id"] == vid


# --- update / delete ---

def test_update_blocked_when_posted(ctx):
    vid = _make_video(ctx)
    with ctx.Session() as db:
        db.add(ScheduledPost(
            video_id=uuid.UUID(vid), platform="youtube", status="posted",
            title="t", description="d",
        ))
        db.commit()
    resp = ctx.client.patch(f"/api/posts/{vid}", json={"theme": "new"})
    assert resp.status_code == 409


def test_update_theme(ctx):
    vid = _make_video(ctx)
    resp = ctx.client.patch(f"/api/posts/{vid}", json={"theme": "新テーマ", "memo": "m"})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "新テーマ"


def test_delete(ctx):
    vid = _make_video(ctx)
    assert ctx.client.delete(f"/api/posts/{vid}").status_code == 204
    assert ctx.client.get(f"/api/posts/{vid}").status_code == 404
