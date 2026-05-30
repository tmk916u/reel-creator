"""投稿機能（social-publishing）の DB 基盤。

Phase 1 ではマイグレーションツール（Alembic）は導入せず、
起動時に `init_db()` で `create_all` する。スキーマが安定し
たら Alembic を導入する。
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://reel:reel@db:5432/reel",
)


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """全テーブルを作成する（存在すれば no-op）。"""
    from app.models import db_models  # noqa: F401  モデル登録のため

    Base.metadata.create_all(bind=engine)
