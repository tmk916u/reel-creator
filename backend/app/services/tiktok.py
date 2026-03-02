import os
import time
import requests


TIKTOK_API_BASE = "https://open.tiktokapis.com"
UPLOAD_POLL_INTERVAL = 5  # seconds
UPLOAD_TIMEOUT = 300  # 5 minutes


def publish_to_tiktok(video_path: str, caption: str, hashtags: str) -> dict:
    """Publish a video to TikTok.

    Args:
        video_path: Local file path of the video
        caption: Post caption/title
        hashtags: Hashtag string to append to caption

    Returns:
        dict with 'success', 'post_id', 'message' keys
    """
    full_caption = f"{caption}\n\n{hashtags}".strip() if hashtags else caption

    try:
        file_size = os.path.getsize(video_path)
        init_data = _init_upload(file_size, full_caption)
        publish_id = init_data["publish_id"]
        upload_url = init_data["upload_url"]

        _upload_video(upload_url, video_path)
        status = _check_status(publish_id)

        return {"success": True, "post_id": publish_id, "message": "TikTok投稿完了"}
    except Exception as e:
        return {"success": False, "post_id": None, "message": f"TikTok投稿失敗: {str(e)}"}


def _get_credentials() -> tuple[str, str, str]:
    """Get TikTok API credentials from environment"""
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    access_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not access_token:
        raise RuntimeError("TikTok credentials not configured")
    return client_key, client_secret, access_token


def _init_upload(file_size: int, caption: str) -> dict:
    """Initialize video upload and return publish_id and upload_url"""
    _, _, access_token = _get_credentials()

    resp = requests.post(
        f"{TIKTOK_API_BASE}/v2/post/publish/inbox/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        error_msg = data.get("error", {}).get("message", "Unknown error")
        raise RuntimeError(f"TikTok upload init failed: {error_msg}")

    return {
        "publish_id": data["data"]["publish_id"],
        "upload_url": data["data"]["upload_url"],
    }


def _upload_video(upload_url: str, video_path: str) -> None:
    """Upload video file to TikTok's upload URL"""
    file_size = os.path.getsize(video_path)

    with open(video_path, "rb") as f:
        resp = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                "Content-Type": "video/mp4",
            },
            data=f,
            timeout=300,
        )
        resp.raise_for_status()


def _check_status(publish_id: str, timeout: int = UPLOAD_TIMEOUT) -> dict:
    """Poll publish status until complete or timeout"""
    _, _, access_token = _get_credentials()
    start = time.time()

    while time.time() - start < timeout:
        resp = requests.post(
            f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("data", {}).get("status")

        if status == "PUBLISH_COMPLETE":
            return data
        if status in ("FAILED", "PUBLISH_FAILED"):
            fail_reason = data.get("data", {}).get("fail_reason", "Unknown")
            raise RuntimeError(f"TikTok publish failed: {fail_reason}")

        time.sleep(UPLOAD_POLL_INTERVAL)

    raise RuntimeError("TikTok publish timed out")
