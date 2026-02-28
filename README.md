# Reel Creator

TikTok/Instagramリール配信用の動画を簡単に作成するWebアプリ。

## 機能

- 動画アップロード（MP4/MOV/WebM、最大3分）
- 無音部分の自動検出・削除
- AI字幕の自動生成（オプション、faster-whisper使用）
- 処理進捗のリアルタイム表示（SSE）
- 処理結果サマリーとダウンロード

## クイックスタート

```bash
# リポジトリをクローン
git clone <repository-url>
cd reel-creator

# Docker Composeで起動
docker compose up --build
```

- フロントエンド: http://localhost:3000
- バックエンドAPI: http://localhost:8000
- ヘルスチェック: http://localhost:8000/api/health

## 使い方

1. http://localhost:3000 にアクセス
2. 縦型動画（9:16）をドラッグ&ドロップでアップロード
3. 無音削除の設定を調整（閾値、最小無音長）
4. オプションでAI字幕を有効化（フォントサイズ・位置・色を選択）
5. 「動画を処理する」をクリック
6. 処理完了後、プレビュー確認してダウンロード

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| Frontend | Next.js 16, TypeScript, Tailwind CSS v4 |
| Backend | FastAPI, Python 3.11 |
| 動画処理 | FFmpeg |
| 音声認識 | faster-whisper (base model, CPU, int8) |
| インフラ | Docker Compose |
| フォント | Noto Sans CJK JP（日本語字幕用） |

## API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | /api/health | ヘルスチェック |
| POST | /api/upload | 動画アップロード |
| POST | /api/process/{job_id} | 処理開始 |
| GET | /api/progress/{job_id} | 進捗SSEストリーム |
| GET | /api/result/{job_id} | 処理結果取得 |
| GET | /api/download/{job_id} | 動画ダウンロード |

## プロジェクト構成

```
reel-creator/
├── frontend/              # Next.js 16 (App Router)
│   ├── app/               # ページ
│   ├── components/        # UIコンポーネント
│   └── lib/               # APIクライアント
├── backend/               # FastAPI
│   ├── app/
│   │   ├── routers/       # APIエンドポイント
│   │   ├── services/      # ビジネスロジック
│   │   └── models/        # Pydanticスキーマ
│   └── tests/             # pytestテスト
├── docs/                  # ドキュメント
│   ├── requirements.md    # 要件定義書
│   ├── test-spec.md       # テスト仕様書
│   └── plans/             # 設計・実装計画
└── docker-compose.yml
```

## 開発

### バックエンドテスト

```bash
cd backend
pip install pytest
PYTHONPATH=. pytest tests/ -v
```

### ローカル開発（Docker不使用）

```bash
# バックエンド
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# フロントエンド（別ターミナル）
cd frontend
npm install
npm run dev
```

## ライセンス

Private
