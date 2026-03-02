import asyncio
import shutil
import time
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import video, publish

TMP_DIR = Path("/app/tmp")
CLEANUP_INTERVAL = 300  # 5 minutes
MAX_AGE = 3600  # 1 hour


async def cleanup_old_jobs():
    """Delete old job directories periodically"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        if TMP_DIR.exists():
            now = time.time()
            for job_dir in TMP_DIR.iterdir():
                if job_dir.is_dir() and (now - job_dir.stat().st_mtime) > MAX_AGE:
                    shutil.rmtree(job_dir, ignore_errors=True)


@asynccontextmanager
async def lifespan(app_instance):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(cleanup_old_jobs())
    yield
    task.cancel()


app = FastAPI(title="Reel Creator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video.router)
app.include_router(publish.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
