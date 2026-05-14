# Reel Creator

TikTok/Instagramリール配信用の動画を簡単に作成するWebアプリ。

## 機能

- 動画アップロード（MP4/MOV/WebM、最大3分）
- 無音部分の自動検出・削除
- **AIジャンプカット**: フィラーワード（「えーっと」「あのー」等）・言い直し・長い間を自動で削減
- AI字幕の自動生成（オプション、faster-whisper使用）
- 処理進捗のリアルタイム表示（SSE）
- 処理結果サマリーとダウンロード
- SNS自動投稿（Instagram Reels / TikTok）
- Google Sheetsからキャプション・ハッシュタグ取得

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
| POST | /api/publish/{job_id} | SNS自動投稿 |
| GET | /api/media/{job_id} | 動画配信（Instagram API用） |

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

## SNS自動投稿の設定

### 1. Google Sheets サービスアカウント

1. Google Cloud Consoleでサービスアカウントを作成
2. Google Sheets APIを有効化
3. JSONキーをダウンロードし `backend/credentials/service_account.json` に配置
4. スプレッドシートをサービスアカウントのメールアドレスに共有

### 2. 環境変数の設定

`backend/.env` を編集:

```env
GOOGLE_SHEETS_CREDENTIALS_JSON=/app/credentials/service_account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id

INSTAGRAM_ACCESS_TOKEN=your_token
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_account_id

TIKTOK_CLIENT_KEY=your_key
TIKTOK_CLIENT_SECRET=your_secret
TIKTOK_ACCESS_TOKEN=your_token

PUBLIC_BASE_URL=https://your-public-url.com
```

## AIジャンプカット

設定パネルの「AIジャンプカット」をONにすると、以下を自動で削除します：

- **フィラー削除**: 日本語フィラー辞書（`backend/app/data/jp_fillers.txt`）に基づく機械的検出
- **言い直し・噛み検出**: Whisper transcript を LLM に渡して判定
- **文末テンポカット**: 句読点の後の長い間（>0.4秒）を 0.2秒に短縮

### LLM プロバイダ設定

言い直し検出には LLM API を使用します。`backend/.env` に以下を設定：

```env
# openai または anthropic
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=
```

`LLM_PROVIDER` 未設定または API キー欠落の場合は **degraded mode** で動作し、
言い直し検出のみスキップしてフィラー削除と文末カットで処理を継続します。

### 3. Google Sheets列構成（13列）

| 列 | 内容 |
|----|------|
| A | # |
| B | ステータス |
| C | アカウント |
| D | 投稿予定日 |
| E | 投稿実績日 |
| F | プラットフォーム |
| G | テーマ |
| H | フック |
| I | 台本/内容概要 |
| J | IGキャプション |
| K | TikTokキャプション |
| L | ハッシュタグ |
| M | 備考 |

### 4. 投稿APIの使い方

```bash
# 処理済み動画をInstagramとTikTokに投稿（シート3行目のデータを使用）
curl -X POST http://localhost:8000/api/publish/{job_id} \
  -H "Content-Type: application/json" \
  -d '{"sheet_row": 3, "platforms": ["instagram", "tiktok"]}'
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
