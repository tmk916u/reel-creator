import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.routers import connections as conn_mod
from app.routers.connections import router as conn_router


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    app.include_router(conn_router)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_list_empty(client):
    assert client.get("/api/connections").json() == []


def test_youtube_start_not_configured_redirects(client, monkeypatch):
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
    resp = client.get("/api/connections/youtube/start", follow_redirects=False)
    assert resp.status_code == 303
    assert "youtube_error=not_configured" in resp.headers["location"]


def test_youtube_callback_saves_connection(client, monkeypatch):
    monkeypatch.setattr(
        conn_mod.youtube,
        "exchange_code",
        lambda code: {
            "refresh_token": "rt",
            "access_token": "at",
            "token_expires_at": None,
            "external_account_id": "CH1",
            "account_name": "My Channel",
        },
    )
    resp = client.get(
        "/api/connections/youtube/callback?code=abc&state=s", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "connected=youtube" in resp.headers["location"]

    rows = client.get("/api/connections").json()
    assert len(rows) == 1
    assert rows[0]["platform"] == "youtube"
    assert rows[0]["account_name"] == "My Channel"
    assert rows[0]["is_active"] is True
    assert "token" not in rows[0]  # トークンは返さない


def test_youtube_callback_error_redirects(client):
    resp = client.get(
        "/api/connections/youtube/callback?error=access_denied", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "youtube_error=access_denied" in resp.headers["location"]


# --- Meta / Instagram ---

def test_meta_start_not_configured_redirects(client, monkeypatch):
    for k in ("META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
    resp = client.get("/api/connections/meta/start", follow_redirects=False)
    assert resp.status_code == 303
    assert "instagram_error=not_configured" in resp.headers["location"]


def test_meta_callback_saves_connection(client, monkeypatch):
    monkeypatch.setattr(
        conn_mod.instagram,
        "exchange_meta_code",
        lambda code: {
            "access_token": "page_long_token",
            "refresh_token": None,
            "token_expires_at": None,
            "external_account_id": "IG123",
            "account_name": "my_ig",
        },
    )
    resp = client.get(
        "/api/connections/meta/callback?code=abc&state=s", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "connected=instagram" in resp.headers["location"]

    rows = client.get("/api/connections").json()
    assert len(rows) == 1
    assert rows[0]["platform"] == "instagram"
    assert rows[0]["account_name"] == "my_ig"
    assert rows[0]["external_account_id"] == "IG123"
    assert rows[0]["is_active"] is True


def test_meta_callback_error_redirects(client):
    resp = client.get(
        "/api/connections/meta/callback?error=user_denied", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "instagram_error=user_denied" in resp.headers["location"]
