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


def _create_container(
    video_url: str,
    caption: str,
    access_token: str | None = None,
    account_id: str | None = None,
) -> str:
    """Create a media container for Reels upload"""
    if access_token is None or account_id is None:
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


def _wait_for_container(
    container_id: str,
    timeout: int = CONTAINER_TIMEOUT,
    access_token: str | None = None,
) -> None:
    """Poll container status until FINISHED or timeout"""
    if access_token is None:
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


def _publish_container(
    container_id: str,
    access_token: str | None = None,
    account_id: str | None = None,
) -> str:
    """Publish the processed container"""
    if access_token is None or account_id is None:
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


# ===== Phase 3: Instagram Login flow + connection ベース投稿 =====

# 新フロー（Instagram API with Instagram Login）:
# - 認証: instagram.com の OAuth dialog（FB ページ経由不要）
# - 投稿: graph.instagram.com のエンドポイント（graph.facebook.com ではない）

INSTAGRAM_OAUTH_AUTHORIZE = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_OAUTH_TOKEN = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH = "https://graph.instagram.com/v23.0"
INSTAGRAM_GRAPH_ROOT = "https://graph.instagram.com"
META_SCOPES = (
    "instagram_business_basic,"
    "instagram_business_content_publish"
)


def publish_to_instagram_with(
    video_url: str,
    caption: str,
    *,
    access_token: str,
    ig_account_id: str,
) -> dict:
    """連携トークン (IG Login) を使って Reels を投稿する。"""
    try:
        container_id = _ig_create_container(
            video_url, caption, access_token=access_token, ig_user_id=ig_account_id
        )
        _ig_wait_for_container(container_id, access_token=access_token)
        post_id = _ig_publish_container(
            container_id, access_token=access_token, ig_user_id=ig_account_id
        )
        return {"success": True, "post_id": post_id, "message": "Instagram投稿完了"}
    except Exception as e:
        return {"success": False, "post_id": None, "message": f"Instagram投稿失敗: {e}"}


def fetch_permalink(post_id: str, *, access_token: str) -> str | None:
    """投稿後の permalink を取得する（失敗時 None）。"""
    try:
        r = requests.get(
            f"{INSTAGRAM_GRAPH}/{post_id}",
            params={"fields": "permalink", "access_token": access_token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("permalink")
    except Exception:
        return None


def _ig_create_container(video_url, caption, *, access_token, ig_user_id):
    resp = requests.post(
        f"{INSTAGRAM_GRAPH}/{ig_user_id}/media",
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


def _ig_wait_for_container(container_id, *, access_token, timeout=CONTAINER_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"{INSTAGRAM_GRAPH}/{container_id}",
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


def _ig_publish_container(container_id, *, access_token, ig_user_id):
    resp = requests.post(
        f"{INSTAGRAM_GRAPH}/{ig_user_id}/media_publish",
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


def _meta_env() -> tuple[str, str, str]:
    cid = os.environ.get("META_APP_ID", "")
    secret = os.environ.get("META_APP_SECRET", "")
    redirect = os.environ.get("META_REDIRECT_URI", "")
    if not (cid and secret and redirect):
        raise RuntimeError(
            "Meta OAuth 未設定: META_APP_ID / META_APP_SECRET / META_REDIRECT_URI を設定してください"
        )
    return cid, secret, redirect


def build_meta_auth_url(state: str) -> str:
    """Instagram OAuth (Instagram Login) 同意 URL を生成する。"""
    from urllib.parse import urlencode

    cid, _, redirect = _meta_env()
    params = urlencode(
        {
            "client_id": cid,
            "redirect_uri": redirect,
            "state": state,
            "response_type": "code",
            "scope": META_SCOPES,
        }
    )
    return f"{INSTAGRAM_OAUTH_AUTHORIZE}?{params}"


def exchange_meta_code(code: str) -> dict:
    """認可コード → 長期 IG Business トークン + アカウント情報。"""
    from datetime import datetime, timedelta, timezone

    cid, secret, redirect = _meta_env()

    # 1) 短期トークン（1 時間）
    r = requests.post(
        INSTAGRAM_OAUTH_TOKEN,
        data={
            "client_id": cid,
            "client_secret": secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
            "code": code,
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    short_token = body["access_token"]
    initial_user_id = str(body.get("user_id") or body.get("id") or "")

    # 2) 長期トークン（60 日）
    r = requests.get(
        f"{INSTAGRAM_GRAPH_ROOT}/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": secret,
            "access_token": short_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    long_data = r.json()
    long_token = long_data["access_token"]
    expires_in = long_data.get("expires_in")
    token_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in else None
    )

    # 3) ユーザー情報（username / 投稿 API で使う IG Business アカウント ID）
    ig_user_id = initial_user_id
    username = None
    try:
        me = requests.get(
            f"{INSTAGRAM_GRAPH}/me",
            params={"fields": "id,username,user_id", "access_token": long_token},
            timeout=30,
        )
        if me.status_code == 200:
            me_data = me.json()
            ig_user_id = str(me_data.get("user_id") or me_data.get("id") or initial_user_id)
            username = me_data.get("username")
    except Exception:
        pass

    if not ig_user_id:
        raise RuntimeError("Instagram ビジネスアカウントの ID を取得できませんでした")

    return {
        "access_token": long_token,
        "refresh_token": None,
        "token_expires_at": token_expires_at,
        "external_account_id": ig_user_id,
        "account_name": username,
    }
