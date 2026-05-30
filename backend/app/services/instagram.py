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


# ===== Phase 3: connection ベース投稿 + Meta OAuth =====

META_DIALOG_OAUTH = "https://www.facebook.com/v21.0/dialog/oauth"
META_SCOPES = (
    "instagram_basic,instagram_content_publish,"
    "pages_show_list,business_management"
)


def publish_to_instagram_with(
    video_url: str,
    caption: str,
    *,
    access_token: str,
    ig_account_id: str,
) -> dict:
    """連携トークンを明示指定して Reels を投稿する。"""
    try:
        container_id = _create_container(
            video_url, caption, access_token=access_token, account_id=ig_account_id
        )
        _wait_for_container(container_id, access_token=access_token)
        post_id = _publish_container(
            container_id, access_token=access_token, account_id=ig_account_id
        )
        return {"success": True, "post_id": post_id, "message": "Instagram投稿完了"}
    except Exception as e:
        return {"success": False, "post_id": None, "message": f"Instagram投稿失敗: {e}"}


def fetch_permalink(post_id: str, *, access_token: str) -> str | None:
    """投稿後の permalink を取得する（失敗時 None）。"""
    try:
        r = requests.get(
            f"{GRAPH_API_BASE}/{post_id}",
            params={"fields": "permalink", "access_token": access_token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("permalink")
    except Exception:
        return None


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
    """Facebook Login 同意 URL を生成する。"""
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
    return f"{META_DIALOG_OAUTH}?{params}"


def exchange_meta_code(code: str) -> dict:
    """認可コード → 長期 page token + IG ビジネスアカウント情報。"""
    cid, secret, redirect = _meta_env()

    # 1) short-lived user token
    r = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "client_id": cid,
            "client_secret": secret,
            "redirect_uri": redirect,
            "code": code,
        },
        timeout=30,
    )
    r.raise_for_status()
    short_user = r.json()["access_token"]

    # 2) long-lived user token
    r = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": cid,
            "client_secret": secret,
            "fb_exchange_token": short_user,
        },
        timeout=30,
    )
    r.raise_for_status()
    long_user = r.json()["access_token"]

    # 3) pages
    r = requests.get(
        f"{GRAPH_API_BASE}/me/accounts",
        params={"access_token": long_user},
        timeout=30,
    )
    r.raise_for_status()
    pages = r.json().get("data", [])

    # 4) find IG business account on a page
    for p in pages:
        ig_resp = requests.get(
            f"{GRAPH_API_BASE}/{p['id']}",
            params={
                "fields": "instagram_business_account{id,username}",
                "access_token": long_user,
            },
            timeout=30,
        )
        if ig_resp.status_code != 200:
            continue
        ig = ig_resp.json().get("instagram_business_account")
        if ig and ig.get("id"):
            return {
                "access_token": p["access_token"],  # 長期 page token（IG 投稿に使う）
                "refresh_token": None,
                "token_expires_at": None,
                "external_account_id": ig["id"],
                "account_name": ig.get("username") or p.get("name"),
            }

    raise RuntimeError(
        "Instagram ビジネスアカウントが連携された Facebook ページが見つかりません"
    )
