import os
from unittest.mock import patch, MagicMock, mock_open
import pytest
from app.services.tiktok import publish_to_tiktok, _init_upload, _upload_video


@patch.dict("os.environ", {
    "TIKTOK_CLIENT_KEY": "test_key",
    "TIKTOK_CLIENT_SECRET": "test_secret",
    "TIKTOK_ACCESS_TOKEN": "test_token",
})
class TestTikTok:

    @patch("app.services.tiktok.requests.post")
    @patch("app.services.tiktok.requests.put")
    @patch("app.services.tiktok.os.path.getsize", return_value=1024)
    @patch("builtins.open", mock_open(read_data=b"fake_video_data"))
    def test_publish_success(self, mock_getsize, mock_put, mock_post):
        # Init response
        init_resp = MagicMock()
        init_resp.json.return_value = {
            "error": {"code": "ok"},
            "data": {"publish_id": "pub_123", "upload_url": "https://upload.tiktok.com/video"},
        }
        init_resp.raise_for_status = MagicMock()

        # Status response
        status_resp = MagicMock()
        status_resp.json.return_value = {
            "data": {"status": "PUBLISH_COMPLETE"},
        }
        status_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [init_resp, status_resp]

        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()
        mock_put.return_value = put_resp

        result = publish_to_tiktok("/tmp/video.mp4", "Test caption", "#test")
        assert result["success"] is True
        assert result["post_id"] == "pub_123"

    @patch("app.services.tiktok.requests.post")
    def test_init_upload_error(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {
            "error": {"code": "invalid_token", "message": "Token expired"},
        }
        resp.raise_for_status = MagicMock()
        mock_post.return_value = resp

        with pytest.raises(RuntimeError, match="TikTok upload init failed"):
            _init_upload(1024, "caption")

    @patch("app.services.tiktok.requests.post")
    @patch("app.services.tiktok.os.path.getsize", return_value=1024)
    @patch("builtins.open", mock_open(read_data=b"fake_video_data"))
    def test_publish_failure(self, mock_getsize, mock_post):
        init_resp = MagicMock()
        init_resp.json.return_value = {
            "error": {"code": "ok"},
            "data": {"publish_id": "pub_999", "upload_url": "https://upload.tiktok.com/video"},
        }
        init_resp.raise_for_status = MagicMock()

        status_resp = MagicMock()
        status_resp.json.return_value = {
            "data": {"status": "PUBLISH_FAILED", "fail_reason": "Video too short"},
        }
        status_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [init_resp, status_resp]

        # Need to also mock put for the upload step
        with patch("app.services.tiktok.requests.put") as mock_put:
            put_resp = MagicMock()
            put_resp.raise_for_status = MagicMock()
            mock_put.return_value = put_resp

            result = publish_to_tiktok("/tmp/video.mp4", "caption", "")
            assert result["success"] is False
            assert "失敗" in result["message"]
