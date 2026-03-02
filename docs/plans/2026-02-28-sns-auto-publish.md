# SNS自動投稿機能 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 処理済み動画をGoogle Sheetsのキャプション/ハッシュタグを使ってInstagram Reels・TikTokに自動投稿する機能を追加する

**Architecture:** 既存のvideo routerとは独立したpublish routerを新設。Google Sheets連携・Instagram API・TikTok APIをそれぞれ独立したserviceとして実装し、publish routerがオーケストレーションする。

**Tech Stack:** FastAPI, gspread, google-auth, requests, python-dotenv

---

### Task 1: .env / 環境変数の設定

**Files:**
- Create: `backend/.env`
- Create: `backend/.env.example`
- Modify: `backend/docker-compose.yml` (ルート)
- Modify: `backend/app/main.py`

**Step 1: .env.example を作成**

```env
# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON=/app/credentials/service_account.json
GOOGLE_SHEETS_SPREADSHEET_ID=

# Instagram (Graph API)
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_BUSINESS_ACCOUNT_ID=

# TikTok (Content Posting API)
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
TIKTOK_ACCESS_TOKEN=

# App Settings
PUBLIC_BASE_URL=http://localhost:8000
```

**Step 2: .env を作成（同じ内容、.gitignoreに追加）**

**Step 3: docker-compose.yml に env_file を追加**

backend serviceに `env_file: ./backend/.env` を追加。

**Step 4: .gitignore に .env と credentials/ を追加**

**Step 5: requirements.txt に依存を追加**

`gspread`, `google-auth`, `python-dotenv` を追加。

---

### Task 2: Google Sheets サービス

**Files:**
- Create: `backend/app/services/google_sheets.py`
- Create: `backend/tests/test_google_sheets.py`

**実装内容:**

```python
# 列マッピング定数
COLUMNS = {
    "id": 0, "status": 1, "account": 2, "scheduled_date": 3,
    "posted_date": 4, "platform": 5, "theme": 6, "hook": 7,
    "script": 8, "ig_caption": 9, "tiktok_caption": 10,
    "hashtags": 11, "notes": 12,
}

class SheetRow(BaseModel):
    row_number: int
    status: str
    account: str
    platform: str
    ig_caption: str
    tiktok_caption: str
    hashtags: str

def get_sheet_client() -> gspread.Spreadsheet
def get_row_data(row_number: int) -> SheetRow
def update_post_status(row_number: int, platform: str) -> None
    # ステータス列 → "投稿済み"
    # 投稿実績日 → 今日の日付 (YYYY/MM/DD)
```

**テスト:** gspread clientをモックして、get_row_data / update_post_status の動作を検証。

---

### Task 3: Instagram Reels 投稿サービス

**Files:**
- Create: `backend/app/services/instagram.py`
- Create: `backend/tests/test_instagram.py`

**実装内容:**

Instagram Graph APIのReels投稿は3ステップ:
1. コンテナ作成（POST /{ig-user-id}/media）— video_url, caption, media_type=REELS
2. ステータス確認ポーリング（GET /{container-id}?fields=status_code）
3. 公開（POST /{ig-user-id}/media_publish）— creation_id

```python
def publish_to_instagram(video_url: str, caption: str, hashtags: str) -> dict:
    """Instagram Reelsに動画を投稿し、結果を返す"""

def _create_container(video_url: str, caption: str) -> str:
    """メディアコンテナを作成してIDを返す"""

def _wait_for_container(container_id: str, timeout: int = 120) -> bool:
    """コンテナのステータスがFINISHEDになるまでポーリング"""

def _publish_container(container_id: str) -> str:
    """コンテナを公開してメディアIDを返す"""
```

**テスト:** requests をモックしてAPI呼び出しの正常系・エラー系を検証。

---

### Task 4: TikTok 投稿サービス

**Files:**
- Create: `backend/app/services/tiktok.py`
- Create: `backend/tests/test_tiktok.py`

**実装内容:**

TikTok Content Posting APIのフロー:
1. 投稿初期化（POST /v2/post/publish/inbox/video/init）
2. 動画アップロード（PUT upload_url）
3. ステータス確認（GET /v2/post/publish/status/fetch）

```python
def publish_to_tiktok(video_path: str, caption: str, hashtags: str) -> dict:
    """TikTokに動画を投稿し、結果を返す"""

def _init_upload(file_size: int) -> dict:
    """アップロード初期化してupload_url, publish_idを返す"""

def _upload_video(upload_url: str, video_path: str) -> None:
    """チャンクアップロードで動画を送信"""

def _check_status(publish_id: str, timeout: int = 120) -> dict:
    """公開ステータスを確認"""
```

**テスト:** requests をモックしてAPI呼び出しの正常系・エラー系を検証。

---

### Task 5: Publishスキーマ追加

**Files:**
- Modify: `backend/app/models/schemas.py`

**追加モデル:**

```python
class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"

class PublishRequest(BaseModel):
    sheet_row: int
    platforms: list[Platform]

class PublishResult(BaseModel):
    platform: str
    success: bool
    message: str
    post_id: str | None = None

class PublishResponse(BaseModel):
    job_id: str
    results: list[PublishResult]
```

---

### Task 6: Publish ルーター & main.py 統合

**Files:**
- Create: `backend/app/routers/publish.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_publish_router.py`

**エンドポイント:**

```python
@router.post("/publish/{job_id}", response_model=PublishResponse)
async def publish_video(job_id: str, req: PublishRequest):
    # 1. output.mp4 の存在確認
    # 2. Google Sheetsからキャプション・ハッシュタグ取得
    # 3. platforms毎に投稿実行
    #    - instagram → publish_to_instagram(video_url, caption, hashtags)
    #    - tiktok → publish_to_tiktok(video_path, caption, hashtags)
    # 4. 成功したplatformのシートステータスを更新
    # 5. PublishResponseを返す
```

**Instagram用の動画URL公開:**
処理済み動画を一時的にHTTPで配信するエンドポイント `/api/media/{job_id}` を追加（Instagram Graph APIはURLが必要なため）。

**main.py変更:**
`app.include_router(publish.router)` を追加。

**テスト:** FastAPI TestClientで正常系・エラー系を検証（サービス層はモック）。

---

### Task 7: ドキュメント更新

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

SNS投稿機能のセクション追加、新しいエンドポイントの記載、環境変数の設定手順を追記。
