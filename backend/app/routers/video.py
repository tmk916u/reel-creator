# backend/app/routers/video.py
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.schemas import UploadResponse
from app.services.ffmpeg import get_video_duration

router = APIRouter(prefix="/api", tags=["video"])

TMP_DIR = Path("/app/tmp")
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_DURATION = 180  # 3 minutes
ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


@router.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    job_id = str(uuid.uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / "input.mp4"
    file_size = 0
    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                shutil.rmtree(job_dir)
                raise HTTPException(400, "File too large (max 500MB)")
            f.write(chunk)

    try:
        duration = get_video_duration(str(input_path))
    except RuntimeError:
        shutil.rmtree(job_dir)
        raise HTTPException(400, "Invalid video file")

    if duration > MAX_DURATION:
        shutil.rmtree(job_dir)
        raise HTTPException(400, f"Video too long ({duration:.1f}s, max {MAX_DURATION}s)")

    return UploadResponse(
        job_id=job_id,
        filename=file.filename or "video.mp4",
        duration=round(duration, 2),
        file_size=file_size,
    )
