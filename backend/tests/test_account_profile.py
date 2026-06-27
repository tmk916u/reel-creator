from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.routers.profile import router as profile_router
from app.services.account_profile import build_caption_system_prompt


# --- build_caption_system_prompt (純粋関数) ---

def test_prompt_falls_back_to_default_niche_when_empty():
    prompt = build_caption_system_prompt(None)
    assert "整体院 / ヘルスケア領域" in prompt
    assert "アカウント文脈" not in prompt  # 文脈ブロックは出ない


def test_prompt_uses_custom_niche():
    prompt = build_caption_system_prompt({"niche": "パーソナルジム"})
    assert "パーソナルジム のリール動画" in prompt
    assert "整体院" not in prompt


def test_prompt_injects_account_context_block():
    prompt = build_caption_system_prompt({
        "niche": "カフェ",
        "target_audience": "20代女性",
        "tone": "やさしい敬語",
        "goals": "来店促進",
        "hashtags": "#カフェ巡り",
        "ng_words": "激安",
        "notes": "季節メニュー推し",
    })
    assert "【アカウント文脈】" in prompt
    assert "ターゲット視聴者: 20代女性" in prompt
    assert "トーン/語り口: やさしい敬語" in prompt
    assert "運用目的: 来店促進" in prompt
    assert "#カフェ巡り" in prompt
    assert "避ける語/表現（使用禁止）: 激安" in prompt
    assert "季節メニュー推し" in prompt


def test_prompt_always_contains_json_schema():
    prompt = build_caption_system_prompt({"niche": "x"})
    assert "instagram_caption" in prompt
    assert "cover_text_candidates" in prompt


def test_prompt_blank_strings_treated_as_unset():
    prompt = build_caption_system_prompt({"niche": "  ", "target_audience": ""})
    assert "整体院 / ヘルスケア領域" in prompt
    assert "アカウント文脈" not in prompt


# --- router GET/PUT ---

@dataclass
class Ctx:
    client: TestClient


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = FastAPI()
    app.include_router(profile_router)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return Ctx(client=TestClient(app))


def test_get_creates_empty_profile(ctx):
    resp = ctx.client.get("/api/account-profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["niche"] is None
    assert "id" in body


def test_put_updates_and_persists(ctx):
    resp = ctx.client.put(
        "/api/account-profile",
        json={"niche": "整骨院", "target_audience": "30-40代"},
    )
    assert resp.status_code == 200
    assert resp.json()["niche"] == "整骨院"

    # 再取得しても同じプロファイル（単一・永続）
    again = ctx.client.get("/api/account-profile")
    assert again.json()["niche"] == "整骨院"
    assert again.json()["target_audience"] == "30-40代"


def test_put_is_singleton(ctx):
    first = ctx.client.put("/api/account-profile", json={"niche": "A"}).json()
    second = ctx.client.put("/api/account-profile", json={"niche": "B"}).json()
    assert first["id"] == second["id"]
    assert ctx.client.get("/api/account-profile").json()["niche"] == "B"


def test_put_partial_does_not_clear_other_fields(ctx):
    ctx.client.put("/api/account-profile", json={"niche": "A", "tone": "丁寧"})
    ctx.client.put("/api/account-profile", json={"niche": "B"})
    body = ctx.client.get("/api/account-profile").json()
    assert body["niche"] == "B"
    assert body["tone"] == "丁寧"
