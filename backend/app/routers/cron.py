"""予約投稿の手動 / 外部トリガーエンドポイント（design D6）。

APScheduler が 1 分間隔で自動実行するが、これは手動 or 外部 cron からの
バックアップとして使う。CRON_SECRET ヘッダ必須。
"""
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.publisher import run_due_posts

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/run")
def trigger_cron(
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
    db: Session = Depends(get_db),
):
    expected = os.environ.get("CRON_SECRET", "")
    if not expected or x_cron_secret != expected:
        raise HTTPException(401, "invalid cron secret")
    processed = run_due_posts(db)
    return {"processed": processed}
