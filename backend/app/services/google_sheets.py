import os
from datetime import date
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column mapping for the 13-column sheet structure
COLUMNS = {
    "id": 0,              # A: #
    "status": 1,          # B: ステータス
    "account": 2,         # C: アカウント
    "scheduled_date": 3,  # D: 投稿予定日
    "posted_date": 4,     # E: 投稿実績日
    "platform": 5,        # F: プラットフォーム
    "theme": 6,           # G: テーマ
    "hook": 7,            # H: フック
    "script": 8,          # I: 台本/内容概要
    "ig_caption": 9,      # J: IGキャプション
    "tiktok_caption": 10, # K: TikTokキャプション
    "hashtags": 11,       # L: ハッシュタグ
    "notes": 12,          # M: 備考
}


class SheetRow(BaseModel):
    row_number: int
    status: str
    account: str
    platform: str
    ig_caption: str
    tiktok_caption: str
    hashtags: str


def get_sheet_client() -> gspread.Spreadsheet:
    """Get authenticated Google Sheets client"""
    creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")

    if not creds_path or not spreadsheet_id:
        raise RuntimeError("Google Sheets credentials or spreadsheet ID not configured")

    credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(credentials)
    return client.open_by_key(spreadsheet_id)


def get_row_data(row_number: int) -> SheetRow:
    """Fetch a single row from the sheet (1-indexed, row 1 is header)"""
    spreadsheet = get_sheet_client()
    worksheet = spreadsheet.sheet1
    values = worksheet.row_values(row_number)

    # Pad with empty strings if row has fewer columns
    while len(values) < 13:
        values.append("")

    return SheetRow(
        row_number=row_number,
        status=values[COLUMNS["status"]],
        account=values[COLUMNS["account"]],
        platform=values[COLUMNS["platform"]],
        ig_caption=values[COLUMNS["ig_caption"]],
        tiktok_caption=values[COLUMNS["tiktok_caption"]],
        hashtags=values[COLUMNS["hashtags"]],
    )


def update_post_status(row_number: int) -> None:
    """Update status to '投稿済み' and posted_date to today"""
    spreadsheet = get_sheet_client()
    worksheet = spreadsheet.sheet1

    # Status column (B) = col 2, Posted date column (E) = col 5 (1-indexed)
    worksheet.update_cell(row_number, COLUMNS["status"] + 1, "投稿済み")
    worksheet.update_cell(row_number, COLUMNS["posted_date"] + 1, date.today().strftime("%Y/%m/%d"))


def write_captions_to_sheet(
    row_number: int,
    ig_caption: str,
    tiktok_caption: str,
    hashtags: str,
) -> None:
    """生成されたキャプションとハッシュタグをシートに書き込む。"""
    spreadsheet = get_sheet_client()
    worksheet = spreadsheet.sheet1

    worksheet.update_cell(row_number, COLUMNS["ig_caption"] + 1, ig_caption)
    worksheet.update_cell(row_number, COLUMNS["tiktok_caption"] + 1, tiktok_caption)
    worksheet.update_cell(row_number, COLUMNS["hashtags"] + 1, hashtags)
