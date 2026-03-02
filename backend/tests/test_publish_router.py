from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@patch("app.routers.publish.TMP_DIR", Path("/tmp/test_publish"))
class TestPublishRouter:

    def setup_method(self):
        """Create a fake output.mp4 for each test"""
        job_dir = Path("/tmp/test_publish/test-job-id")
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "output.mp4").write_bytes(b"fake_video")

    def teardown_method(self):
        import shutil
        shutil.rmtree("/tmp/test_publish", ignore_errors=True)

    def test_publish_job_not_found(self):
        resp = client.post("/api/publish/nonexistent", json={
            "sheet_row": 2,
            "platforms": ["instagram"],
        })
        assert resp.status_code == 404

    @patch("app.routers.publish.update_post_status")
    @patch("app.routers.publish.publish_to_instagram")
    @patch("app.routers.publish.get_row_data")
    def test_publish_instagram_success(self, mock_get_row, mock_ig, mock_update):
        mock_get_row.return_value = MagicMock(
            ig_caption="IG caption", tiktok_caption="TK caption", hashtags="#test"
        )
        mock_ig.return_value = {"success": True, "post_id": "ig_123", "message": "OK"}

        resp = client.post("/api/publish/test-job-id", json={
            "sheet_row": 2,
            "platforms": ["instagram"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["success"] is True
        assert data["results"][0]["platform"] == "instagram"
        mock_update.assert_called_once_with(2)

    @patch("app.routers.publish.update_post_status")
    @patch("app.routers.publish.publish_to_tiktok")
    @patch("app.routers.publish.publish_to_instagram")
    @patch("app.routers.publish.get_row_data")
    def test_publish_both_platforms(self, mock_get_row, mock_ig, mock_tk, mock_update):
        mock_get_row.return_value = MagicMock(
            ig_caption="IG caption", tiktok_caption="TK caption", hashtags="#test"
        )
        mock_ig.return_value = {"success": True, "post_id": "ig_1", "message": "OK"}
        mock_tk.return_value = {"success": True, "post_id": "tk_1", "message": "OK"}

        resp = client.post("/api/publish/test-job-id", json={
            "sheet_row": 3,
            "platforms": ["instagram", "tiktok"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert all(r["success"] for r in data["results"])

    @patch("app.routers.publish.update_post_status")
    @patch("app.routers.publish.publish_to_instagram")
    @patch("app.routers.publish.get_row_data")
    def test_publish_failure_no_sheet_update(self, mock_get_row, mock_ig, mock_update):
        mock_get_row.return_value = MagicMock(
            ig_caption="IG caption", tiktok_caption="", hashtags=""
        )
        mock_ig.return_value = {"success": False, "post_id": None, "message": "Failed"}

        resp = client.post("/api/publish/test-job-id", json={
            "sheet_row": 2,
            "platforms": ["instagram"],
        })
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is False
        mock_update.assert_not_called()

    @patch("app.routers.publish.get_row_data")
    def test_publish_sheets_error(self, mock_get_row):
        mock_get_row.side_effect = RuntimeError("Credentials not configured")

        resp = client.post("/api/publish/test-job-id", json={
            "sheet_row": 2,
            "platforms": ["instagram"],
        })
        assert resp.status_code == 400
        assert "Google Sheets" in resp.json()["detail"]
