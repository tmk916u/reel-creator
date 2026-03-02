from unittest.mock import patch, MagicMock
import pytest
from app.services.instagram import publish_to_instagram, _create_container, _wait_for_container, _publish_container


@patch.dict("os.environ", {
    "INSTAGRAM_ACCESS_TOKEN": "test_token",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID": "test_account_id",
})
class TestInstagram:

    @patch("app.services.instagram.requests.post")
    @patch("app.services.instagram.requests.get")
    def test_publish_success(self, mock_get, mock_post):
        # Mock create container
        create_resp = MagicMock()
        create_resp.json.return_value = {"id": "container_123"}
        create_resp.raise_for_status = MagicMock()

        # Mock publish
        publish_resp = MagicMock()
        publish_resp.json.return_value = {"id": "post_456"}
        publish_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [create_resp, publish_resp]

        # Mock status check
        status_resp = MagicMock()
        status_resp.json.return_value = {"status_code": "FINISHED"}
        status_resp.raise_for_status = MagicMock()
        mock_get.return_value = status_resp

        result = publish_to_instagram("https://example.com/video.mp4", "Test caption", "#test")
        assert result["success"] is True
        assert result["post_id"] == "post_456"

    @patch("app.services.instagram.requests.post")
    def test_publish_container_creation_fails(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"error": {"message": "Invalid token"}}
        resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = resp

        result = publish_to_instagram("https://example.com/video.mp4", "caption", "")
        assert result["success"] is False
        assert "失敗" in result["message"]

    @patch("app.services.instagram.requests.post")
    def test_create_container(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"id": "container_789"}
        resp.raise_for_status = MagicMock()
        mock_post.return_value = resp

        container_id = _create_container("https://example.com/v.mp4", "caption")
        assert container_id == "container_789"
        mock_post.assert_called_once()
