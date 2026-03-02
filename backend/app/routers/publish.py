import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    Platform, PublishRequest, PublishResponse, PublishResult,
)
from app.services.google_sheets import get_row_data, update_post_status
from app.services.instagram import publish_to_instagram
from app.services.tiktok import publish_to_tiktok

router = APIRouter(prefix="/api", tags=["publish"])

TMP_DIR = Path("/app/tmp")


@router.post("/publish/{job_id}", response_model=PublishResponse)
async def publish_video(job_id: str, req: PublishRequest):
    """Publish processed video to SNS platforms"""
    output_path = TMP_DIR / job_id / "output.mp4"
    if not output_path.exists():
        raise HTTPException(404, "処理済み動画が見つかりません")

    # Fetch caption & hashtags from Google Sheets
    try:
        row = get_row_data(req.sheet_row)
    except Exception as e:
        raise HTTPException(400, f"Google Sheets読み取りエラー: {str(e)}")

    results: list[PublishResult] = []

    for platform in req.platforms:
        if platform == Platform.INSTAGRAM:
            # Instagram requires a publicly accessible URL
            base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
            video_url = f"{base_url}/api/media/{job_id}"
            res = publish_to_instagram(video_url, row.ig_caption, row.hashtags)
        elif platform == Platform.TIKTOK:
            res = publish_to_tiktok(str(output_path), row.tiktok_caption, row.hashtags)
        else:
            res = {"success": False, "post_id": None, "message": f"未対応プラットフォーム: {platform}"}

        results.append(PublishResult(
            platform=platform.value,
            success=res["success"],
            message=res["message"],
            post_id=res.get("post_id"),
        ))

    # Update sheet status if at least one platform succeeded
    if any(r.success for r in results):
        try:
            update_post_status(req.sheet_row)
        except Exception:
            pass  # Sheet update failure should not fail the whole response

    return PublishResponse(job_id=job_id, results=results)


@router.get("/media/{job_id}")
async def serve_media(job_id: str):
    """Serve processed video file (used by Instagram API for fetching video URL)"""
    from fastapi.responses import FileResponse
    output_path = TMP_DIR / job_id / "output.mp4"
    if not output_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(output_path), media_type="video/mp4")
