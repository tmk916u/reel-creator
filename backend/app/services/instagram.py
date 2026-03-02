import os
import time
import requests


GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
CONTAINER_POLL_INTERVAL = 5  # seconds
CONTAINER_TIMEOUT = 300  # 5 minutes


def publish_to_instagram(video_url: str, caption: str, hashtags: str) -> dict:
    """Publish a video to Instagram Reels.

    Args:
        video_url: Publicly accessible HTTPS URL of the video
        caption: Post caption text
        hashtags: Hashtag string to append to caption

    Returns:
        dict with 'success', 'post_id', 'message' keys
    """
    full_caption = f"{caption}\n\n{hashtags}".strip() if hashtags else caption

    try:
        container_id = _create_container(video_url, full_caption)
        _wait_for_container(container_id)
        post_id = _publish_container(container_id)
        return {"success": True, "post_id": post_id, "message": "Instagram投稿完了"}
    except Exception as e:
        return {"success": False, "post_id": None, "message": f"Instagram投稿失敗: {str(e)}"}


def _get_credentials() -> tuple[str, str]:
    """Get Instagram API credentials from environment"""
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if not access_token or not account_id:
        raise RuntimeError("Instagram credentials not configured")
    return access_token, account_id


def _create_container(video_url: str, caption: str) -> str:
    """Create a media container for Reels upload"""
    access_token, account_id = _get_credentials()

    resp = requests.post(
        f"{GRAPH_API_BASE}/{account_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "id" not in data:
        raise RuntimeError(f"Container creation failed: {data}")
    return data["id"]


def _wait_for_container(container_id: str, timeout: int = CONTAINER_TIMEOUT) -> None:
    """Poll container status until FINISHED or timeout"""
    access_token, _ = _get_credentials()
    start = time.time()

    while time.time() - start < timeout:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram container processing failed")

        time.sleep(CONTAINER_POLL_INTERVAL)

    raise RuntimeError("Instagram container processing timed out")


def _publish_container(container_id: str) -> str:
    """Publish the processed container"""
    access_token, account_id = _get_credentials()

    resp = requests.post(
        f"{GRAPH_API_BASE}/{account_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "id" not in data:
        raise RuntimeError(f"Publishing failed: {data}")
    return data["id"]
