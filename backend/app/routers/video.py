# backend/app/routers/video.py
import uuid
import shutil
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import (
    UploadResponse, ProcessRequest, ProcessResponse, ProgressEvent,
    JobStatus, JobResult, FontSize, SubtitlePosition, SubtitleColor,
)
from app.services.ffmpeg import (
    get_video_duration, extract_audio, detect_silence, cut_and_concat, burn_subtitles,
)
from app.services.silence import compute_voice_segments
from app.services.subtitle import transcribe_audio

router = APIRouter(prefix="/api", tags=["video"])

TMP_DIR = Path("/app/tmp")
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_DURATION = 180  # 3 minutes
ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm"}

# Job state store (in-memory)
job_store: dict[str, dict] = {}


def _font_size_to_px(size: FontSize) -> int:
    return {"small": 16, "medium": 22, "large": 30}[size.value]


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


def _run_processing(job_id: str, settings: ProcessRequest):
    """Run video processing in background"""
    job = job_store[job_id]
    job_dir = TMP_DIR / job_id
    input_path = str(job_dir / "input.mp4")

    try:
        # Stage 1: Audio extraction
        job.update({"stage": "audio_extract", "progress": 10, "message": "音声を抽出中..."})
        audio_path = str(job_dir / "audio.wav")
        extract_audio(input_path, audio_path)

        # Stage 2: Silence detection
        job.update({"stage": "silence_detect", "progress": 30, "message": "無音区間を解析中..."})
        silences = detect_silence(audio_path, settings.silence_threshold, settings.min_silence_duration)
        original_duration = get_video_duration(input_path)
        voice_segments = compute_voice_segments(silences, original_duration)

        if not voice_segments:
            job.update({
                "status": JobStatus.FAILED,
                "stage": "error",
                "progress": 100,
                "message": "有音区間が見つかりませんでした",
            })
            return

        # Stage 3: Cut & concat
        job.update({"stage": "cut_concat", "progress": 50, "message": "無音区間を削除中..."})
        cut_output = str(job_dir / "cut.mp4")
        cut_and_concat(input_path, voice_segments, cut_output)

        processed_duration = get_video_duration(cut_output)
        final_output = cut_output

        # Stage 4: Subtitles (optional)
        if settings.enable_subtitles:
            job.update({"stage": "transcribe", "progress": 70, "message": "字幕を生成中..."})
            cut_audio = str(job_dir / "cut_audio.wav")
            extract_audio(cut_output, cut_audio)
            srt_path = str(job_dir / "subtitles.srt")
            transcribe_audio(cut_audio, srt_path)

            job.update({"stage": "burn_subtitles", "progress": 85, "message": "字幕を動画に焼き込み中..."})
            subtitled_output = str(job_dir / "output.mp4")
            burn_subtitles(
                cut_output, srt_path, subtitled_output,
                font_size=_font_size_to_px(settings.font_size),
                position=settings.subtitle_position.value,
                color=settings.subtitle_color.value,
            )
            final_output = subtitled_output

        # Rename final output
        output_path = job_dir / "output.mp4"
        if str(output_path) != final_output:
            shutil.copy2(final_output, str(output_path))

        silence_removed = original_duration - processed_duration
        job.update({
            "status": JobStatus.COMPLETED,
            "stage": "done",
            "progress": 100,
            "message": "処理が完了しました",
            "original_duration": round(original_duration, 2),
            "processed_duration": round(processed_duration, 2),
            "silence_removed": round(silence_removed, 2),
        })

    except Exception as e:
        job.update({
            "status": JobStatus.FAILED,
            "stage": "error",
            "progress": 100,
            "message": f"処理エラー: {str(e)}",
        })


@router.post("/process/{job_id}", response_model=ProcessResponse)
async def process_video(job_id: str, settings: ProcessRequest, background_tasks: BackgroundTasks):
    job_dir = TMP_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job not found")

    job_store[job_id] = {
        "status": JobStatus.PROCESSING,
        "stage": "init",
        "progress": 0,
        "message": "処理を開始します...",
    }

    background_tasks.add_task(_run_processing, job_id, settings)

    return ProcessResponse(job_id=job_id, status=JobStatus.PROCESSING)


@router.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    async def event_generator():
        while True:
            job = job_store.get(job_id)
            if not job:
                yield {"data": '{"error": "Job not found"}'}
                break

            event = ProgressEvent(
                job_id=job_id,
                status=job["status"],
                stage=job.get("stage", ""),
                progress=job.get("progress", 0),
                message=job.get("message", ""),
            )
            yield {"data": event.model_dump_json()}

            if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/result/{job_id}", response_model=JobResult)
async def get_result(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(400, "Job not completed yet")

    return JobResult(
        job_id=job_id,
        status=job["status"],
        original_duration=job["original_duration"],
        processed_duration=job["processed_duration"],
        silence_removed=job["silence_removed"],
    )


@router.get("/download/{job_id}")
async def download_video(job_id: str):
    output_path = TMP_DIR / job_id / "output.mp4"
    if not output_path.exists():
        raise HTTPException(404, "Output file not found")

    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename=f"reel_{job_id[:8]}.mp4",
    )
