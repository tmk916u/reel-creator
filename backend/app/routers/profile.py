"""アカウント文脈プロファイル（account-context-profile）API。

単一プロファイルを get-or-create で運用し、GET で取得・PUT で更新する。
このプロファイルは AI キャプション生成のシステムプロンプトに注入される。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.schemas import AccountProfileIn, AccountProfileOut
from app.services.account_profile import get_or_create_active

router = APIRouter(prefix="/api/account-profile", tags=["account-profile"])


@router.get("", response_model=AccountProfileOut)
def get_profile(db: Session = Depends(get_db)):
    """アクティブなアカウントプロファイルを取得（無ければ空で作成）。"""
    return get_or_create_active(db)


@router.put("", response_model=AccountProfileOut)
def update_profile(payload: AccountProfileIn, db: Session = Depends(get_db)):
    """アカウントプロファイルを更新する。"""
    profile = get_or_create_active(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
