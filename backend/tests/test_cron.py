import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models.db_models import ScheduledPost, Video
from app.routers import cron as cron_mod
from app.routers.cron import router as cron_router


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    app.include_router(cron_router)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def test_cron_missing_secret_unauthorized(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setenv("CRON_SECRET", "expected")
    resp = client.post("/api/cron/run")
    assert resp.status_code == 401


def test_cron_wrong_secret_unauthorized(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setenv("CRON_SECRET", "expected")
    resp = client.post("/api/cron/run", headers={"X-Cron-Secret": "wrong"})
    assert resp.status_code == 401


def test_cron_unset_env_unauthorized(ctx, monkeypatch):
    """CRON_SECRET 未設定なら何を送っても拒否される（誤発火防止）。"""
    client, _ = ctx
    monkeypatch.delenv("CRON_SECRET", raising=False)
    resp = client.post("/api/cron/run", headers={"X-Cron-Secret": ""})
    assert resp.status_code == 401


def test_cron_correct_secret_runs_publisher(ctx, monkeypatch):
    client, Session = ctx
    monkeypatch.setenv("CRON_SECRET", "expected")

    # publisher.run_due_posts を mock して呼び出しと戻り値を検証
    called = {"n": 0}
    def fake_run_due_posts(db):
        called["n"] += 1
        return 7
    monkeypatch.setattr(cron_mod, "run_due_posts", fake_run_due_posts)

    resp = client.post("/api/cron/run", headers={"X-Cron-Secret": "expected"})
    assert resp.status_code == 200
    assert resp.json() == {"processed": 7}
    assert called["n"] == 1


def test_cron_invokes_publisher_with_db_session(ctx, monkeypatch):
    """run_due_posts に DB セッションが渡されることを確認。"""
    client, Session = ctx
    monkeypatch.setenv("CRON_SECRET", "s")

    seen = {"is_session": False}
    def fake_run_due_posts(db):
        from sqlalchemy.orm import Session as SessionType
        seen["is_session"] = isinstance(db, SessionType)
        return 0
    monkeypatch.setattr(cron_mod, "run_due_posts", fake_run_due_posts)

    resp = client.post("/api/cron/run", headers={"X-Cron-Secret": "s"})
    assert resp.status_code == 200
    assert seen["is_session"] is True
