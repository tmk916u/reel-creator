# Reel Creator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** TikTok/IGリール用の動画を作成するWebアプリ。動画をアップロードすると無音部分を自動削除し、オプションでAI字幕を付与して出力する。

**Architecture:** Next.js 14 (App Router) フロントエンド + FastAPI バックエンド。Docker Composeで一括起動。動画処理はFFmpeg、字幕生成はfaster-whisperを使用。進捗通知はSSE。

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, FastAPI, Python 3.11, FFmpeg, faster-whisper, Docker Compose

**Design Doc:** `docs/plans/2026-02-25-reel-creator-design.md`

---

## Phase 1: プロジェクト基盤

### Task 1: プロジェクトスキャフォールディング

**Files:**
- Create: `reel-creator/docker-compose.yml`
- Create: `reel-creator/backend/Dockerfile`
- Create: `reel-creator/backend/requirements.txt`
- Create: `reel-creator/backend/app/__init__.py`
- Create: `reel-creator/backend/app/main.py`
- Create: `reel-creator/frontend/Dockerfile`

**Step 1: プロジェクトディレクトリとgitリポジトリ作成**

```bash
mkdir -p ~/reel-creator/{backend/app,frontend}
cd ~/reel-creator
git init
```

**Step 2: backend/requirements.txt を作成**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.20
sse-starlette==2.2.1
faster-whisper==1.1.0
pydantic==2.10.5
```

**Step 3: backend/app/main.py を作成**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Reel Creator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

**Step 4: backend/Dockerfile を作成**

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 5: frontend/Dockerfile を作成**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

CMD ["npm", "run", "dev"]
```

**Step 6: docker-compose.yml を作成**

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - backend-tmp:/app/tmp
    environment:
      - PYTHONUNBUFFERED=1

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - backend

volumes:
  backend-tmp:
```

**Step 7: .gitignore を作成**

```
# Python
__pycache__/
*.pyc
.venv/
backend/tmp/

# Node
node_modules/
.next/
frontend/.next/

# OS
.DS_Store

# IDE
.vscode/
.idea/
```

**Step 8: コミット**

```bash
git add -A
git commit -m "chore: scaffold project structure with Docker Compose"
```

---

### Task 2: Next.js フロントエンド初期化

**Files:**
- Create: `reel-creator/frontend/package.json`
- Create: `reel-creator/frontend/next.config.js`
- Create: `reel-creator/frontend/tailwind.config.ts`
- Create: `reel-creator/frontend/tsconfig.json`
- Create: `reel-creator/frontend/postcss.config.js`
- Create: `reel-creator/frontend/app/layout.tsx`
- Create: `reel-creator/frontend/app/page.tsx`
- Create: `reel-creator/frontend/app/globals.css`

**Step 1: Next.js プロジェクトを作成**

```bash
cd ~/reel-creator/frontend
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir=false --import-alias="@/*" --use-npm --no-turbopack
```

**Step 2: app/layout.tsx を日本語対応に修正**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel Creator",
  description: "TikTok/IGリール用動画を簡単作成",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="bg-gray-950 text-white min-h-screen">{children}</body>
    </html>
  );
}
```

**Step 3: app/page.tsx にプレースホルダーを作成**

```tsx
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center">
      <h1 className="text-4xl font-bold">Reel Creator</h1>
      <p className="mt-4 text-gray-400">TikTok/IGリール用動画を簡単作成</p>
    </main>
  );
}
```

**Step 4: 動作確認**

```bash
cd ~/reel-creator
docker compose up --build
# ブラウザで http://localhost:3000 を確認
# ブラウザで http://localhost:8000/api/health を確認 → {"status":"ok"}
```

**Step 5: コミット**

```bash
git add -A
git commit -m "chore: initialize Next.js frontend with Tailwind CSS"
```

---

## Phase 2: バックエンド - 動画処理コア

### Task 3: Pydantic スキーマ定義

**Files:**
- Create: `reel-creator/backend/app/models/__init__.py`
- Create: `reel-creator/backend/app/models/schemas.py`

**Step 1: スキーマを定義**

```python
# backend/app/models/schemas.py
from pydantic import BaseModel
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FontSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class SubtitlePosition(str, Enum):
    BOTTOM = "bottom"
    CENTER = "center"


class SubtitleColor(str, Enum):
    WHITE = "white"
    YELLOW = "yellow"


class ProcessRequest(BaseModel):
    silence_threshold: float = -30.0  # dB
    min_silence_duration: float = 0.5  # seconds
    enable_subtitles: bool = False
    font_size: FontSize = FontSize.MEDIUM
    subtitle_position: SubtitlePosition = SubtitlePosition.BOTTOM
    subtitle_color: SubtitleColor = SubtitleColor.WHITE


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    duration: float
    file_size: int


class ProcessResponse(BaseModel):
    job_id: str
    status: JobStatus


class ProgressEvent(BaseModel):
    job_id: str
    status: JobStatus
    stage: str
    progress: int  # 0-100
    message: str


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    original_duration: float
    processed_duration: float
    silence_removed: float
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add Pydantic schemas for API models"
```

---

### Task 4: FFmpeg ラッパーサービス

**Files:**
- Create: `reel-creator/backend/app/services/__init__.py`
- Create: `reel-creator/backend/app/services/ffmpeg.py`
- Create: `reel-creator/backend/tests/__init__.py`
- Create: `reel-creator/backend/tests/test_ffmpeg.py`

**Step 1: テストを書く**

```python
# backend/tests/test_ffmpeg.py
import pytest
from app.services.ffmpeg import get_video_duration, extract_audio


def test_get_video_duration_invalid_file():
    with pytest.raises(RuntimeError):
        get_video_duration("/nonexistent/file.mp4")
```

**Step 2: テストが失敗することを確認**

```bash
cd ~/reel-creator/backend
pip install pytest
pytest tests/test_ffmpeg.py -v
# Expected: FAIL (ModuleNotFoundError)
```

**Step 3: FFmpegラッパーを実装**

```python
# backend/app/services/ffmpeg.py
import subprocess
import json
import os
from pathlib import Path


def get_video_duration(filepath: str) -> float:
    """FFprobeで動画の長さ（秒）を取得"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_audio(video_path: str, output_path: str) -> str:
    """動画から音声をWAVで抽出"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")
    return output_path


def detect_silence(audio_path: str, threshold: float = -30.0, min_duration: float = 0.5) -> list[dict]:
    """FFmpegのsilencedetectフィルタで無音区間を検出"""
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silences = []
    silence_start = None
    for line in stderr.split("\n"):
        if "silence_start:" in line:
            silence_start = float(line.split("silence_start:")[1].strip().split()[0])
        elif "silence_end:" in line and silence_start is not None:
            parts = line.split("silence_end:")[1].strip().split()
            silence_end = float(parts[0])
            silences.append({"start": silence_start, "end": silence_end})
            silence_start = None

    return silences


def cut_and_concat(video_path: str, segments: list[dict], output_path: str) -> str:
    """有音セグメントをカットして結合"""
    if not segments:
        raise ValueError("No segments to concatenate")

    workdir = Path(output_path).parent / "segments"
    workdir.mkdir(exist_ok=True)
    concat_list = workdir / "concat.txt"

    segment_files = []
    for i, seg in enumerate(segments):
        seg_file = str(workdir / f"seg_{i:04d}.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(seg["start"]),
            "-to", str(seg["end"]),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            seg_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg cut failed for segment {i}: {result.stderr}")
        segment_files.append(seg_file)

    with open(concat_list, "w") as f:
        for sf in segment_files:
            f.write(f"file '{sf}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")

    return output_path


def burn_subtitles(video_path: str, srt_path: str, output_path: str,
                   font_size: int = 20, position: str = "bottom",
                   color: str = "white") -> str:
    """SRT字幕を動画に焼き込む"""
    alignment = 2 if position == "bottom" else 5  # ASS alignment
    color_hex = "&H00FFFFFF" if color == "white" else "&H0000FFFF"

    style = (
        f"FontSize={font_size},"
        f"PrimaryColour={color_hex},"
        f"Alignment={alignment},"
        f"BorderStyle=3,"
        f"Outline=1,"
        f"Shadow=0,"
        f"MarginV=30,"
        f"FontName=Noto Sans CJK JP"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg subtitle burn failed: {result.stderr}")

    return output_path
```

**Step 4: テストを実行して通ることを確認**

```bash
pytest tests/test_ffmpeg.py -v
# Expected: PASS
```

**Step 5: コミット**

```bash
git add -A
git commit -m "feat: add FFmpeg wrapper service with silence detection"
```

---

### Task 5: 無音削除サービス

**Files:**
- Create: `reel-creator/backend/app/services/silence.py`
- Create: `reel-creator/backend/tests/test_silence.py`

**Step 1: テストを書く**

```python
# backend/tests/test_silence.py
from app.services.silence import compute_voice_segments


def test_compute_voice_segments_basic():
    """無音区間から有音区間を正しく算出する"""
    silences = [
        {"start": 2.0, "end": 4.0},
        {"start": 7.0, "end": 9.0},
    ]
    total_duration = 10.0
    result = compute_voice_segments(silences, total_duration)
    assert result == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 7.0},
        {"start": 9.0, "end": 10.0},
    ]


def test_compute_voice_segments_no_silence():
    """無音区間がない場合は動画全体を返す"""
    result = compute_voice_segments([], 10.0)
    assert result == [{"start": 0.0, "end": 10.0}]


def test_compute_voice_segments_all_silence():
    """全体が無音の場合は空リストを返す"""
    silences = [{"start": 0.0, "end": 10.0}]
    result = compute_voice_segments(silences, 10.0)
    assert result == []


def test_compute_voice_segments_silence_at_start():
    """冒頭が無音の場合"""
    silences = [{"start": 0.0, "end": 3.0}]
    result = compute_voice_segments(silences, 10.0)
    assert result == [{"start": 3.0, "end": 10.0}]


def test_compute_voice_segments_adds_padding():
    """パディングを追加した場合"""
    silences = [{"start": 2.0, "end": 5.0}]
    result = compute_voice_segments(silences, 10.0, padding=0.1)
    assert result[0]["end"] == pytest.approx(2.1, abs=0.01)
    assert result[1]["start"] == pytest.approx(4.9, abs=0.01)


# test_silence.py の先頭にimport追加
import pytest
```

**Step 2: テストが失敗することを確認**

```bash
pytest tests/test_silence.py -v
# Expected: FAIL (ModuleNotFoundError)
```

**Step 3: 無音削除ロジックを実装**

```python
# backend/app/services/silence.py


def compute_voice_segments(
    silences: list[dict],
    total_duration: float,
    padding: float = 0.05,
) -> list[dict]:
    """無音区間リストから有音区間リストを算出する。

    Args:
        silences: [{"start": float, "end": float}, ...] 無音区間のリスト
        total_duration: 動画の総再生時間（秒）
        padding: 有音区間の前後に追加するパディング（秒）

    Returns:
        [{"start": float, "end": float}, ...] 有音区間のリスト
    """
    if not silences:
        return [{"start": 0.0, "end": total_duration}]

    # 無音区間をソート
    sorted_silences = sorted(silences, key=lambda s: s["start"])

    segments = []
    current_pos = 0.0

    for silence in sorted_silences:
        seg_start = current_pos
        seg_end = silence["start"]

        # パディング適用
        if padding > 0:
            seg_end = min(seg_end + padding, silence["start"])

        if seg_end > seg_start + 0.01:  # 極小セグメントを除外
            segments.append({"start": round(seg_start, 3), "end": round(seg_end, 3)})

        current_pos = silence["end"]
        if padding > 0:
            current_pos = max(current_pos - padding, silence["end"] - padding)

    # 最後の無音以降の有音部分
    if current_pos < total_duration - 0.01:
        segments.append({"start": round(current_pos, 3), "end": round(total_duration, 3)})

    return segments
```

**Step 4: テストを実行して通ることを確認**

```bash
pytest tests/test_silence.py -v
# Expected: ALL PASS
```

**Step 5: コミット**

```bash
git add -A
git commit -m "feat: add silence removal service with voice segment computation"
```

---

### Task 6: Whisper 字幕生成サービス

**Files:**
- Create: `reel-creator/backend/app/services/subtitle.py`
- Create: `reel-creator/backend/tests/test_subtitle.py`

**Step 1: テストを書く**

```python
# backend/tests/test_subtitle.py
from app.services.subtitle import segments_to_srt


def test_segments_to_srt():
    """Whisperセグメントを正しいSRT形式に変換する"""
    segments = [
        {"start": 0.0, "end": 2.5, "text": "こんにちは"},
        {"start": 3.0, "end": 5.0, "text": "ありがとう"},
    ]
    result = segments_to_srt(segments)
    assert "1\n00:00:00,000 --> 00:00:02,500\nこんにちは" in result
    assert "2\n00:00:03,000 --> 00:00:05,000\nありがとう" in result


def test_segments_to_srt_empty():
    """空のセグメントリストでは空文字列を返す"""
    result = segments_to_srt([])
    assert result == ""
```

**Step 2: テストが失敗することを確認**

```bash
pytest tests/test_subtitle.py -v
# Expected: FAIL
```

**Step 3: 字幕サービスを実装**

```python
# backend/app/services/subtitle.py
from pathlib import Path


def _format_timestamp(seconds: float) -> str:
    """秒数をSRTタイムスタンプ形式に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    """Whisperのセグメントリストをsrt形式の文字列に変換"""
    if not segments:
        return ""

    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    return "\n".join(lines)


def transcribe_audio(audio_path: str, srt_output_path: str) -> str:
    """faster-whisperで音声を文字起こしし、SRTファイルを生成"""
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(audio_path, language="ja")

    segments = []
    for seg in segments_iter:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

    srt_content = segments_to_srt(segments)
    Path(srt_output_path).write_text(srt_content, encoding="utf-8")

    return srt_output_path
```

**Step 4: テストを実行**

```bash
pytest tests/test_subtitle.py -v
# Expected: ALL PASS
```

**Step 5: コミット**

```bash
git add -A
git commit -m "feat: add Whisper subtitle generation service"
```

---

## Phase 3: バックエンド - APIエンドポイント

### Task 7: 動画アップロードAPI

**Files:**
- Create: `reel-creator/backend/app/routers/__init__.py`
- Create: `reel-creator/backend/app/routers/video.py`
- Modify: `reel-creator/backend/app/main.py`

**Step 1: ルーターを実装**

```python
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

    # ファイル保存
    input_path = job_dir / "input.mp4"
    file_size = 0
    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                shutil.rmtree(job_dir)
                raise HTTPException(400, "File too large (max 500MB)")
            f.write(chunk)

    # 動画長チェック
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
```

**Step 2: main.pyにルーターを登録**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import video

app = FastAPI(title="Reel Creator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

**Step 3: コミット**

```bash
git add -A
git commit -m "feat: add video upload API endpoint with validation"
```

---

### Task 8: 動画処理 & 進捗通知API

**Files:**
- Modify: `reel-creator/backend/app/routers/video.py`

**Step 1: 処理・進捗・ダウンロードエンドポイントを追加**

以下を `video.py` に追記する:

```python
# video.py に追加import
import asyncio
from fastapi import BackgroundTasks
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import (
    ProcessRequest, ProcessResponse, ProgressEvent, JobStatus, JobResult,
    FontSize, SubtitlePosition, SubtitleColor,
)
from app.services.ffmpeg import extract_audio, detect_silence, cut_and_concat, burn_subtitles
from app.services.silence import compute_voice_segments
from app.services.subtitle import transcribe_audio

# ジョブの状態管理（インメモリ）
job_store: dict[str, dict] = {}


def _font_size_to_px(size: FontSize) -> int:
    return {"small": 16, "medium": 22, "large": 30}[size.value]


def _run_processing(job_id: str, settings: ProcessRequest):
    """バックグラウンドで動画処理を実行"""
    job = job_store[job_id]
    job_dir = TMP_DIR / job_id
    input_path = str(job_dir / "input.mp4")

    try:
        # Stage 1: 音声抽出
        job.update({"stage": "audio_extract", "progress": 10, "message": "音声を抽出中..."})
        audio_path = str(job_dir / "audio.wav")
        extract_audio(input_path, audio_path)

        # Stage 2: 無音検出
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

        # Stage 3: カット＆結合
        job.update({"stage": "cut_concat", "progress": 50, "message": "無音区間を削除中..."})
        cut_output = str(job_dir / "cut.mp4")
        cut_and_concat(input_path, voice_segments, cut_output)

        processed_duration = get_video_duration(cut_output)
        final_output = cut_output

        # Stage 4: 字幕（オプション）
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

        # 最終ファイルをoutput.mp4にリネーム（まだでなければ）
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
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add processing, progress SSE, and download endpoints"
```

---

### Task 9: 一時ファイル自動クリーンアップ

**Files:**
- Modify: `reel-creator/backend/app/main.py`

**Step 1: スタートアップ時にクリーンアップタスクを登録**

```python
# backend/app/main.py に追加
import asyncio
import shutil
import time
from pathlib import Path
from contextlib import asynccontextmanager

TMP_DIR = Path("/app/tmp")
CLEANUP_INTERVAL = 300  # 5分ごとにチェック
MAX_AGE = 3600  # 1時間で削除


async def cleanup_old_jobs():
    """古いジョブディレクトリを定期削除"""
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


# FastAppのインスタンス生成を更新
app = FastAPI(title="Reel Creator API", lifespan=lifespan)
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add automatic temp file cleanup on 1-hour schedule"
```

---

## Phase 4: フロントエンド

### Task 10: API クライアント

**Files:**
- Create: `reel-creator/frontend/lib/api.ts`

**Step 1: APIクライアントを作成**

```typescript
// frontend/lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UploadResponse {
  job_id: string;
  filename: string;
  duration: number;
  file_size: number;
}

export interface ProcessSettings {
  silence_threshold: number;
  min_silence_duration: number;
  enable_subtitles: boolean;
  font_size: "small" | "medium" | "large";
  subtitle_position: "bottom" | "center";
  subtitle_color: "white" | "yellow";
}

export interface ProgressEvent {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  stage: string;
  progress: number;
  message: string;
}

export interface JobResult {
  job_id: string;
  status: string;
  original_duration: number;
  processed_duration: number;
  silence_removed: number;
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }

  return res.json();
}

export async function startProcessing(
  jobId: string,
  settings: ProcessSettings
): Promise<void> {
  const res = await fetch(`${API_URL}/api/process/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Processing failed");
  }
}

export function subscribeProgress(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  onError: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_URL}/api/progress/${jobId}`);

  eventSource.onmessage = (e) => {
    const data: ProgressEvent = JSON.parse(e.data);
    onEvent(data);

    if (data.status === "completed" || data.status === "failed") {
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    onError(new Error("Connection lost"));
    eventSource.close();
  };

  return () => eventSource.close();
}

export async function getResult(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_URL}/api/result/${jobId}`);
  if (!res.ok) throw new Error("Failed to get result");
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/api/download/${jobId}`;
}
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add TypeScript API client for backend communication"
```

---

### Task 11: VideoUploader コンポーネント

**Files:**
- Create: `reel-creator/frontend/components/VideoUploader.tsx`

**Step 1: アップロードコンポーネントを作成**

```tsx
// frontend/components/VideoUploader.tsx
"use client";

import { useCallback, useState } from "react";

interface Props {
  onUploaded: (jobId: string, duration: number, previewUrl: string) => void;
}

const ACCEPTED_TYPES = ["video/mp4", "video/quicktime", "video/webm"];
const MAX_SIZE = 500 * 1024 * 1024;

export default function VideoUploader({ onUploaded }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setError("対応形式: MP4, MOV, WebM");
        return;
      }
      if (file.size > MAX_SIZE) {
        setError("ファイルサイズは500MB以下にしてください");
        return;
      }

      setUploading(true);
      setProgress(0);

      try {
        const { uploadVideo } = await import("@/lib/api");
        const result = await uploadVideo(file);
        const previewUrl = URL.createObjectURL(file);
        onUploaded(result.job_id, result.duration, previewUrl);
      } catch (e) {
        setError(e instanceof Error ? e.message : "アップロードに失敗しました");
      } finally {
        setUploading(false);
      }
    },
    [onUploaded]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      className={`
        border-2 border-dashed rounded-2xl p-12 text-center transition-colors cursor-pointer
        ${dragOver ? "border-blue-400 bg-blue-400/10" : "border-gray-600 hover:border-gray-400"}
        ${uploading ? "pointer-events-none opacity-60" : ""}
      `}
      onClick={() => {
        if (uploading) return;
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "video/mp4,video/quicktime,video/webm";
        input.onchange = () => {
          const file = input.files?.[0];
          if (file) handleFile(file);
        };
        input.click();
      }}
    >
      {uploading ? (
        <div>
          <div className="text-xl mb-4">アップロード中...</div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : (
        <div>
          <div className="text-5xl mb-4">🎬</div>
          <div className="text-xl mb-2">動画をドラッグ&ドロップ</div>
          <div className="text-gray-400">
            またはクリックしてファイルを選択
          </div>
          <div className="text-gray-500 text-sm mt-4">
            MP4 / MOV / WebM（最大500MB・3分まで）
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4 text-red-400 text-sm">{error}</div>
      )}
    </div>
  );
}
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add VideoUploader component with drag-and-drop"
```

---

### Task 12: ProcessingPanel コンポーネント

**Files:**
- Create: `reel-creator/frontend/components/ProcessingPanel.tsx`

**Step 1: 設定パネルコンポーネントを作成**

```tsx
// frontend/components/ProcessingPanel.tsx
"use client";

import { useState } from "react";
import type { ProcessSettings } from "@/lib/api";

interface Props {
  duration: number;
  previewUrl: string;
  onStart: (settings: ProcessSettings) => void;
}

export default function ProcessingPanel({ duration, previewUrl, onStart }: Props) {
  const [settings, setSettings] = useState<ProcessSettings>({
    silence_threshold: -30,
    min_silence_duration: 0.5,
    enable_subtitles: false,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
  });

  return (
    <div className="space-y-6">
      {/* プレビュー */}
      <div className="flex justify-center">
        <video
          src={previewUrl}
          controls
          className="rounded-xl max-h-[400px]"
        />
      </div>

      <div className="text-center text-gray-400">
        動画の長さ: {duration.toFixed(1)}秒
      </div>

      {/* 設定 */}
      <div className="bg-gray-800 rounded-xl p-6 space-y-5">
        <h3 className="text-lg font-semibold">処理設定</h3>

        {/* 無音閾値 */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            無音の閾値: {settings.silence_threshold}dB
          </label>
          <input
            type="range"
            min={-50}
            max={-10}
            step={1}
            value={settings.silence_threshold}
            onChange={(e) =>
              setSettings((s) => ({ ...s, silence_threshold: Number(e.target.value) }))
            }
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>敏感（-50dB）</span>
            <span>鈍感（-10dB）</span>
          </div>
        </div>

        {/* 最小無音長 */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            最小無音長: {settings.min_silence_duration}秒
          </label>
          <input
            type="range"
            min={0.1}
            max={3.0}
            step={0.1}
            value={settings.min_silence_duration}
            onChange={(e) =>
              setSettings((s) => ({ ...s, min_silence_duration: Number(e.target.value) }))
            }
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>短い無音も削除</span>
            <span>長い無音のみ削除</span>
          </div>
        </div>

        {/* 字幕トグル */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-300">AI字幕を追加</span>
          <button
            onClick={() =>
              setSettings((s) => ({ ...s, enable_subtitles: !s.enable_subtitles }))
            }
            className={`
              relative w-12 h-6 rounded-full transition-colors
              ${settings.enable_subtitles ? "bg-blue-500" : "bg-gray-600"}
            `}
          >
            <span
              className={`
                absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform
                ${settings.enable_subtitles ? "translate-x-6" : ""}
              `}
            />
          </button>
        </div>

        {/* 字幕オプション */}
        {settings.enable_subtitles && (
          <div className="space-y-3 pl-4 border-l-2 border-blue-500/30">
            <div>
              <label className="block text-sm text-gray-400 mb-1">フォントサイズ</label>
              <div className="flex gap-2">
                {(["small", "medium", "large"] as const).map((size) => (
                  <button
                    key={size}
                    onClick={() => setSettings((s) => ({ ...s, font_size: size }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.font_size === size
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ small: "小", medium: "中", large: "大" }[size]}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">位置</label>
              <div className="flex gap-2">
                {(["bottom", "center"] as const).map((pos) => (
                  <button
                    key={pos}
                    onClick={() => setSettings((s) => ({ ...s, subtitle_position: pos }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.subtitle_position === pos
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ bottom: "下部", center: "中央" }[pos]}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">文字色</label>
              <div className="flex gap-2">
                {(["white", "yellow"] as const).map((color) => (
                  <button
                    key={color}
                    onClick={() => setSettings((s) => ({ ...s, subtitle_color: color }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.subtitle_color === color
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ white: "白", yellow: "黄色" }[color]}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 処理開始ボタン */}
      <button
        onClick={() => onStart(settings)}
        className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-xl text-lg font-semibold transition-colors"
      >
        動画を処理する
      </button>
    </div>
  );
}
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: add ProcessingPanel component with settings UI"
```

---

### Task 13: ProgressView & DownloadPanel コンポーネント

**Files:**
- Create: `reel-creator/frontend/components/ProgressView.tsx`
- Create: `reel-creator/frontend/components/DownloadPanel.tsx`

**Step 1: 進捗表示コンポーネント**

```tsx
// frontend/components/ProgressView.tsx
"use client";

import type { ProgressEvent } from "@/lib/api";

interface Props {
  event: ProgressEvent;
}

export default function ProgressView({ event }: Props) {
  return (
    <div className="text-center space-y-6">
      {/* アニメーション */}
      <div className="text-6xl animate-pulse">
        {{ audio_extract: "🎵", silence_detect: "🔍", cut_concat: "✂️",
           transcribe: "💬", burn_subtitles: "📝", done: "✅", error: "❌",
           init: "⏳" }[event.stage] || "⚙️"}
      </div>

      {/* メッセージ */}
      <div className="text-xl">{event.message}</div>

      {/* プログレスバー */}
      <div className="w-full max-w-md mx-auto">
        <div className="bg-gray-700 rounded-full h-3">
          <div
            className="bg-blue-500 h-3 rounded-full transition-all duration-500"
            style={{ width: `${event.progress}%` }}
          />
        </div>
        <div className="text-gray-400 text-sm mt-2">{event.progress}%</div>
      </div>
    </div>
  );
}
```

**Step 2: ダウンロードパネル**

```tsx
// frontend/components/DownloadPanel.tsx
"use client";

import type { JobResult } from "@/lib/api";
import { getDownloadUrl } from "@/lib/api";

interface Props {
  jobId: string;
  result: JobResult;
  onReset: () => void;
}

export default function DownloadPanel({ jobId, result, onReset }: Props) {
  return (
    <div className="text-center space-y-6">
      <div className="text-6xl">✅</div>
      <h2 className="text-2xl font-bold">処理が完了しました！</h2>

      {/* 処理結果サマリー */}
      <div className="bg-gray-800 rounded-xl p-6 max-w-md mx-auto">
        <div className="grid grid-cols-2 gap-4 text-left">
          <div>
            <div className="text-gray-400 text-sm">元の長さ</div>
            <div className="text-lg">{result.original_duration.toFixed(1)}秒</div>
          </div>
          <div>
            <div className="text-gray-400 text-sm">処理後の長さ</div>
            <div className="text-lg">{result.processed_duration.toFixed(1)}秒</div>
          </div>
          <div className="col-span-2">
            <div className="text-gray-400 text-sm">削除された無音</div>
            <div className="text-lg text-blue-400">
              {result.silence_removed.toFixed(1)}秒
              ({((result.silence_removed / result.original_duration) * 100).toFixed(0)}% 短縮)
            </div>
          </div>
        </div>
      </div>

      {/* プレビュー */}
      <video
        src={getDownloadUrl(jobId)}
        controls
        className="rounded-xl max-h-[400px] mx-auto"
      />

      {/* ボタン */}
      <div className="flex gap-4 justify-center">
        <a
          href={getDownloadUrl(jobId)}
          download
          className="px-8 py-3 bg-blue-600 hover:bg-blue-500 rounded-xl text-lg font-semibold transition-colors"
        >
          ダウンロード
        </a>
        <button
          onClick={onReset}
          className="px-8 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl text-lg transition-colors"
        >
          もう1本作る
        </button>
      </div>
    </div>
  );
}
```

**Step 3: コミット**

```bash
git add -A
git commit -m "feat: add ProgressView and DownloadPanel components"
```

---

### Task 14: メインページの組み立て

**Files:**
- Modify: `reel-creator/frontend/app/page.tsx`

**Step 1: page.tsx にウィザードフローを実装**

```tsx
// frontend/app/page.tsx
"use client";

import { useState, useCallback } from "react";
import VideoUploader from "@/components/VideoUploader";
import ProcessingPanel from "@/components/ProcessingPanel";
import ProgressView from "@/components/ProgressView";
import DownloadPanel from "@/components/DownloadPanel";
import {
  startProcessing,
  subscribeProgress,
  getResult,
  type ProcessSettings,
  type ProgressEvent,
  type JobResult,
} from "@/lib/api";

type Step = "upload" | "settings" | "processing" | "done";

export default function Home() {
  const [step, setStep] = useState<Step>("upload");
  const [jobId, setJobId] = useState("");
  const [duration, setDuration] = useState(0);
  const [previewUrl, setPreviewUrl] = useState("");
  const [progressEvent, setProgressEvent] = useState<ProgressEvent | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUploaded = useCallback(
    (id: string, dur: number, url: string) => {
      setJobId(id);
      setDuration(dur);
      setPreviewUrl(url);
      setStep("settings");
    },
    []
  );

  const handleStartProcessing = useCallback(
    async (settings: ProcessSettings) => {
      setStep("processing");
      setError(null);

      try {
        await startProcessing(jobId, settings);

        subscribeProgress(
          jobId,
          async (event) => {
            setProgressEvent(event);

            if (event.status === "completed") {
              const jobResult = await getResult(jobId);
              setResult(jobResult);
              setStep("done");
            } else if (event.status === "failed") {
              setError(event.message);
              setStep("settings");
            }
          },
          (err) => {
            setError(err.message);
            setStep("settings");
          }
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "処理の開始に失敗しました");
        setStep("settings");
      }
    },
    [jobId]
  );

  const handleReset = useCallback(() => {
    setStep("upload");
    setJobId("");
    setDuration(0);
    setPreviewUrl("");
    setProgressEvent(null);
    setResult(null);
    setError(null);
  }, []);

  return (
    <main className="min-h-screen flex flex-col">
      {/* ヘッダー */}
      <header className="py-6 text-center border-b border-gray-800">
        <h1 className="text-3xl font-bold">Reel Creator</h1>
        <p className="text-gray-400 mt-1">TikTok/IGリール用動画を簡単作成</p>
      </header>

      {/* ステップインジケーター */}
      <div className="flex justify-center gap-2 py-4">
        {(["upload", "settings", "processing", "done"] as const).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                step === s
                  ? "bg-blue-500 text-white"
                  : i < ["upload", "settings", "processing", "done"].indexOf(step)
                  ? "bg-blue-500/30 text-blue-300"
                  : "bg-gray-700 text-gray-500"
              }`}
            >
              {i + 1}
            </div>
            {i < 3 && <div className="w-8 h-px bg-gray-700" />}
          </div>
        ))}
      </div>

      {/* コンテンツ */}
      <div className="flex-1 flex items-start justify-center p-6">
        <div className="w-full max-w-lg">
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {step === "upload" && <VideoUploader onUploaded={handleUploaded} />}
          {step === "settings" && (
            <ProcessingPanel
              duration={duration}
              previewUrl={previewUrl}
              onStart={handleStartProcessing}
            />
          )}
          {step === "processing" && progressEvent && (
            <ProgressView event={progressEvent} />
          )}
          {step === "done" && result && (
            <DownloadPanel jobId={jobId} result={result} onReset={handleReset} />
          )}
        </div>
      </div>
    </main>
  );
}
```

**Step 2: コミット**

```bash
git add -A
git commit -m "feat: assemble main page with 4-step wizard flow"
```

---

## Phase 5: 統合テスト & 仕上げ

### Task 15: Docker Compose で統合テスト

**Step 1: ビルドして起動**

```bash
cd ~/reel-creator
docker compose up --build
```

**Step 2: 手動テスト**

1. http://localhost:3000 にアクセス
2. 短い縦型動画（MP4）をアップロード
3. デフォルト設定で「動画を処理する」をクリック
4. 進捗バーが動くことを確認
5. 完了後、ダウンロードして再生確認
6. 字幕ON で再度テスト

**Step 3: 問題があれば修正してコミット**

```bash
git add -A
git commit -m "fix: resolve integration issues found during testing"
```

---

### Task 16: README 作成 & 最終コミット

**Files:**
- Create: `reel-creator/README.md`

**Step 1: README を作成**

```markdown
# Reel Creator

TikTok/Instagramリール配信用の動画を簡単に作成するWebアプリ。

## 機能

- 動画アップロード（MP4/MOV/WebM、最大3分）
- 無音部分の自動検出・削除
- AI字幕の自動生成（オプション）
- 処理進捗のリアルタイム表示

## 起動方法

```bash
docker compose up --build
```

- フロントエンド: http://localhost:3000
- バックエンドAPI: http://localhost:8000

## 技術スタック

- Frontend: Next.js 14, TypeScript, Tailwind CSS
- Backend: FastAPI, FFmpeg, faster-whisper
- Infrastructure: Docker Compose
```

**Step 2: 最終コミット**

```bash
git add -A
git commit -m "docs: add README with setup instructions"
```

---

## タスク一覧サマリー

| # | タスク | フェーズ |
|---|--------|---------|
| 1 | プロジェクトスキャフォールディング | 基盤 |
| 2 | Next.js フロントエンド初期化 | 基盤 |
| 3 | Pydantic スキーマ定義 | バックエンド |
| 4 | FFmpeg ラッパーサービス | バックエンド |
| 5 | 無音削除サービス | バックエンド |
| 6 | Whisper 字幕生成サービス | バックエンド |
| 7 | 動画アップロードAPI | API |
| 8 | 動画処理 & 進捗通知API | API |
| 9 | 一時ファイル自動クリーンアップ | API |
| 10 | API クライアント | フロントエンド |
| 11 | VideoUploader コンポーネント | フロントエンド |
| 12 | ProcessingPanel コンポーネント | フロントエンド |
| 13 | ProgressView & DownloadPanel | フロントエンド |
| 14 | メインページの組み立て | フロントエンド |
| 15 | Docker Compose 統合テスト | テスト |
| 16 | README 作成 & 最終コミット | 仕上げ |
