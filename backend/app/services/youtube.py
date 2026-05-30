"""YouTube 連携・投稿（design D11）。

Google OAuth 2.0（web フロー）でアカウント連携し、refresh_token を保存。
投稿時は refresh_token から Credentials を再構築して videos.insert で
動画をアップロードする（Shorts は縦動画 + 短尺で自動判定される）。
"""
import os
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


def _env() -> tuple[str, str, str]:
    cid = os.getenv("GOOGLE_CLIENT_ID", "")
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect = os.getenv("GOOGLE_REDIRECT_URI", "")
    if not (cid and secret and redirect):
        raise RuntimeError(
            "Google OAuth 未設定: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI を設定してください"
        )
    return cid, secret, redirect


def _client_config() -> dict:
    cid, secret, redirect = _env()
    return {
        "web": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [redirect],
        }
    }


def _flow() -> Flow:
    _, _, redirect = _env()
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = redirect
    return flow


def build_auth_url(state: str) -> str:
    """同意画面 URL を生成する。refresh_token を確実に得るため prompt=consent。"""
    flow = _flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str) -> dict:
    """認可コードを token に交換し、連携情報を返す。"""
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    channel_id, channel_title = _get_channel(creds)
    return {
        "refresh_token": creds.refresh_token,
        "access_token": creds.token,
        "token_expires_at": creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
        "external_account_id": channel_id,
        "account_name": channel_title,
    }


def _credentials_from_refresh(refresh_token: str) -> Credentials:
    cid, secret, _ = _env()
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=SCOPES,
    )


def _get_channel(creds: Credentials) -> tuple[str | None, str | None]:
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["id"], items[0]["snippet"]["title"]
    except Exception:
        pass
    return None, None


def upload_video(
    refresh_token: str,
    file_path: str,
    *,
    title: str,
    description: str,
    privacy_status: str = "public",
    tags: list[str] | None = None,
) -> dict:
    """videos.insert で動画を投稿し、{video_id, url} を返す。"""
    creds = _credentials_from_refresh(refresh_token)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()

    video_id = response["id"]
    return {"video_id": video_id, "url": f"https://youtu.be/{video_id}"}
