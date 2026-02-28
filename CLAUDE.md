# CLAUDE.md - Reel Creator

## Project Overview
TikTok/IGリール用動画の無音削除＋AI字幕付与Webアプリ

## Tech Stack
- Frontend: Next.js 16 + TypeScript + Tailwind CSS v4
- Backend: FastAPI + Python 3.11
- Video: FFmpeg + faster-whisper
- Infra: Docker Compose

## Commands

### Start
```bash
docker compose up --build     # 全サービス起動
make up                       # 同上（Makefile使用）
```

### Backend
```bash
cd backend
PYTHONPATH=. pytest tests/ -v  # テスト実行
uvicorn app.main:app --reload  # ローカル起動
```

### Frontend
```bash
cd frontend
npm run dev                    # ローカル起動
npm run build                  # ビルド
```

## Architecture

- `frontend/app/page.tsx` — 4ステップウィザード（メインUI）
- `frontend/components/` — UIコンポーネント群
- `frontend/lib/api.ts` — バックエンドAPIクライアント
- `backend/app/main.py` — FastAPIエントリポイント
- `backend/app/routers/video.py` — 全APIエンドポイント
- `backend/app/services/ffmpeg.py` — FFmpegラッパー
- `backend/app/services/silence.py` — 無音削除ロジック
- `backend/app/services/subtitle.py` — Whisper字幕生成
- `backend/app/models/schemas.py` — Pydanticスキーマ

## Conventions
- Backend: Python, snake_case, type hints
- Frontend: TypeScript, camelCase, Tailwind CSS utility classes
- API: RESTful, /api prefix, JSON
- Commits: Conventional Commits (feat/fix/chore/docs)
- Language: UI and docs in Japanese, code in English
