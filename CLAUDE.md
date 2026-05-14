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
- `backend/app/routers/video.py` — 動画処理APIエンドポイント
- `backend/app/routers/publish.py` — SNS投稿APIエンドポイント
- `backend/app/services/ffmpeg.py` — FFmpegラッパー
- `backend/app/services/silence.py` — 無音削除ロジック（extra_cutsで追加削除区間もマージ可）
- `backend/app/services/subtitle.py` — Whisper字幕生成（word-level対応）
- `backend/app/services/jump_cut.py` — AIジャンプカット（フィラー・テンポ・区間マージ）
- `backend/app/services/llm.py` — 言い直し検出用LLMクライアント（OpenAI/Anthropic切替）
- `backend/app/data/jp_fillers.txt` — 日本語フィラー辞書
- `backend/app/services/google_sheets.py` — Google Sheets連携
- `backend/app/services/instagram.py` — Instagram Reels投稿
- `backend/app/services/tiktok.py` — TikTok投稿
- `backend/app/models/schemas.py` — Pydanticスキーマ
- `backend/.env` — 環境変数（gitignored）

## Conventions
- Backend: Python, snake_case, type hints
- Frontend: TypeScript, camelCase, Tailwind CSS utility classes
- API: RESTful, /api prefix, JSON
- Commits: Conventional Commits (feat/fix/chore/docs)
- Language: UI and docs in Japanese, code in English
