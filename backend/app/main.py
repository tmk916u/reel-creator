import asyncio
import logging
import shutil
import time
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import video, publish, posts, connections, cron, profile
from app.db import init_db, SessionLocal
from app.services.publisher import run_due_posts

TMP_DIR = Path("/app/tmp")
CLEANUP_INTERVAL = 300  # 5 minutes
MAX_AGE = 86400  # 24 hours


async def cleanup_old_jobs():
    """Delete old job directories periodically"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        if TMP_DIR.exists():
            now = time.time()
            for job_dir in TMP_DIR.iterdir():
                if job_dir.is_dir() and (now - job_dir.stat().st_mtime) > MAX_AGE:
                    shutil.rmtree(job_dir, ignore_errors=True)


async def _run_due_posts_scheduled():
    """予約時刻到来分を投稿する（APScheduler から呼ばれる）。"""
    def _sync():
        db = SessionLocal()
        try:
            return run_due_posts(db)
        finally:
            db.close()
    try:
        n = await asyncio.get_event_loop().run_in_executor(None, _sync)
        if n:
            logging.info("scheduled publisher: %d 件処理", n)
    except Exception:
        logging.exception("scheduled publisher 失敗")


@asynccontextmanager
async def lifespan(app_instance):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        init_db()
    except Exception:
        logging.exception("DB 初期化に失敗しました")

    cleanup_task = asyncio.create_task(cleanup_old_jobs())

    # 予約投稿スケジューラ
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(_run_due_posts_scheduled, "interval", minutes=1, id="run_due_posts")
        scheduler.start()
        logging.info("予約投稿スケジューラを起動しました (1 分間隔)")
    except Exception:
        logging.exception("スケジューラ起動に失敗しました（手動 cron でも代替可能）")

    yield

    cleanup_task.cancel()
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Reel Creator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video.router)
app.include_router(publish.router)
app.include_router(posts.router)
app.include_router(connections.router)
app.include_router(cron.router)
app.include_router(profile.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
