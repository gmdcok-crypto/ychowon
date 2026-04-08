"""MySQL/MariaDB 전용. Railway 등에서 DATABASE_URL 필수."""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def database_enabled() -> bool:
    """항상 DB 저장소 사용 (JSON 파일 폴백 없음)."""
    return True


def require_database_url() -> str:
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError(
            "DATABASE_URL 환경 변수가 없습니다. Railway MySQL 변수를 서비스에 연결하거나 "
            "mysql://USER:PASSWORD@HOST:PORT/DB 형식으로 설정하세요."
        )
    return raw


def normalize_database_url(url: str) -> str:
    u = url.strip()
    if u.startswith("mysql://"):
        return "mysql+pymysql://" + u[len("mysql://") :]
    if u.startswith("mysql+pymysql://"):
        return u
    raise ValueError("DATABASE_URL은 mysql:// 또는 mysql+pymysql:// 로 시작해야 합니다.")


def get_engine():
    global _engine
    if _engine is None:
        url = normalize_database_url(require_database_url())
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=280,
            echo=False,
            connect_args={"charset": "utf8mb4"},
        )
    return _engine


def SessionLocal() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal()


def init_db() -> None:
    from db_models import Base

    Base.metadata.create_all(bind=get_engine())
