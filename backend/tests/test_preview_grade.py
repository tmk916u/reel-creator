from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import video as video_module
from app.services.ffmpeg import build_preview_vf


# --- build_preview_vf (純粋関数) ---

def test_preview_vf_none_only_scales():
    assert build_preview_vf(None, 360) == "scale=360:-2"


def test_preview_vf_with_lut_applies_lut_first():
    vf = build_preview_vf("/luts/cinematic.cube", 360)
    assert vf == "lut3d=file=/luts/cinematic.cube,scale=360:-2"
    # LUT はスケールより前
    assert vf.index("lut3d") < vf.index("scale")


def test_preview_vf_width_int_coerced():
    assert build_preview_vf(None, 240) == "scale=240:-2"


# --- /api/preview/{job_id}/grade/{grade} エンドポイント ---

def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(video_module, "TMP_DIR", tmp_path)
    app = FastAPI()
    app.include_router(video_module.router)
    return TestClient(app)


def _make_job(tmp_path, job_id="job-prev"):
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "input.mp4").write_bytes(b"fake")
    return job_id, job_dir


def test_preview_unknown_grade_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    job_id, _ = _make_job(tmp_path)
    resp = client.get(f"/api/preview/{job_id}/grade/sepia")
    assert resp.status_code == 404


def test_preview_missing_input_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/preview/nope/grade/cinematic")
    assert resp.status_code == 404


def test_preview_none_passes_no_lut(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    job_id, _ = _make_job(tmp_path)
    captured = {}

    def fake_extract(inp, out, *, lut_path, timestamp, width=360):
        captured["lut_path"] = lut_path
        with open(out, "wb") as f:
            f.write(b"\xff\xd8\xff")  # JPEG マジック
        return out

    monkeypatch.setattr(video_module, "get_video_duration", lambda p: 10.0)
    monkeypatch.setattr(video_module, "extract_grade_preview", fake_extract)

    resp = client.get(f"/api/preview/{job_id}/grade/none")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert captured["lut_path"] is None


def test_preview_caches_second_call(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    job_id, _ = _make_job(tmp_path)
    calls = {"n": 0}

    def fake_extract(inp, out, *, lut_path, timestamp, width=360):
        calls["n"] += 1
        with open(out, "wb") as f:
            f.write(b"\xff\xd8\xff")
        return out

    monkeypatch.setattr(video_module, "get_video_duration", lambda p: 10.0)
    monkeypatch.setattr(video_module, "resolve_lut_path", lambda g, d: f"/luts/{g}.cube")
    monkeypatch.setattr(video_module, "extract_grade_preview", fake_extract)

    r1 = client.get(f"/api/preview/{job_id}/grade/cinematic")
    r2 = client.get(f"/api/preview/{job_id}/grade/cinematic")
    assert r1.status_code == 200 and r2.status_code == 200
    assert calls["n"] == 1  # 2 回目はキャッシュ
