"""MySQL/MariaDB 연결.

- 로컬: ``DATABASE_URL`` 또는 ``MYSQL_URL`` 이 있으면 DB, 없으면 ``data/*.json``
- Railway: 항상 DB만 사용 (아래 URL 중 하나 필수, 없으면 기동 실패)

Railway MySQL은 웹 서비스에 ``DATABASE_URL`` 대신 ``MYSQL_URL`` 만 노출되는 경우가 있어 둘 다 지원합니다.
"""

from __future__ import annotations

import os
import sys
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _mysql_url_from_railway_split_vars() -> str:
    """Railway MySQL 템플릿: MYSQLHOST / MYSQLUSER / MYSQLPASSWORD / MYSQLPORT / MYSQLDATABASE 만 있을 때."""
    host = (os.environ.get("MYSQLHOST") or "").strip()
    user = (os.environ.get("MYSQLUSER") or "").strip()
    password = os.environ.get("MYSQLPASSWORD")
    password = password.strip() if isinstance(password, str) else ""
    port = (os.environ.get("MYSQLPORT") or "3306").strip() or "3306"
    database = (os.environ.get("MYSQLDATABASE") or "").strip()
    if not host or not user or not database:
        return ""
    # 비밀번호에 @ # 등이 있어도 안전하게 이스케이프
    u = quote_plus(user)
    p = quote_plus(password)
    return f"mysql://{u}:{p}@{host}:{port}/{database}"


def database_url_effective() -> str:
    """연결 문자열 후보를 순서대로 사용.

    Railway는 웹 서비스에 ``DATABASE_URL`` 을 안 주고 MySQL 서비스 변수만 참조한 경우가 많습니다.
    그때는 ``MYSQL_URL`` 이 오거나, ``MYSQLHOST`` + ``MYSQLUSER`` + … 조합으로만 옵니다.
    """
    for key in (
        "DATABASE_URL",
        "MYSQL_URL",
        "MYSQLDATABASE_URL",
        "MYSQL_PUBLIC_URL",
    ):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return _mysql_url_from_railway_split_vars()


def running_on_railway() -> bool:
    """Railway 컨테이너에서 실행 중인지 (배포·railway run 등)."""
    return bool((os.environ.get("RAILWAY_ENVIRONMENT") or "").strip())


def database_enabled() -> bool:
    """DB 저장소 사용 여부. Railway에서는 URL 유무와 관계없이 True(파일 폴백 없음)."""
    if database_url_effective():
        return True
    return running_on_railway()


def ensure_railway_database_url_or_exit() -> None:
    """Railway인데 MySQL URL이 없으면 프로세스 종료."""
    if not running_on_railway():
        return
    if database_url_effective():
        return
    print(
        "오류: Railway 배포에서는 MySQL 연결 정보가 필요합니다.\n"
        "아래 중 하나를 웹 서비스 Variables에 넣으세요.\n"
        "  · DATABASE_URL 또는 MYSQL_URL (= ${{MySQL.MYSQL_URL}} 등으로 참조)\n"
        "  · 또는 MYSQLHOST, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE (및 MYSQLPORT)\n"
        "    를 MySQL 서비스에서 웹 서비스로 참조 추가\n"
        "Railway 대시보드: MySQL 서비스 → Connect / Variables → 웹 서비스에 연결",
        file=sys.stderr,
    )
    raise SystemExit(1)


def validate_mysql_database_url_or_exit() -> None:
    """연결 URL이 있으면 MySQL 형식인지 검사 (Postgres 등 잘못 연결 시 안내)."""
    raw = database_url_effective()
    if not raw:
        return
    scheme = raw.split("://", 1)[0].lower() if "://" in raw else ""
    if scheme in ("postgresql", "postgres", "sqlite"):
        print(
            f"오류: DATABASE_URL 스킴이 `{scheme}` 입니다. 이 앱은 MySQL(MariaDB)만 지원합니다.\n"
            "Railway → MySQL 리소스 추가 → 웹 서비스 Variables에 해당 MySQL의 연결 URL을 "
            "DATABASE_URL로 넣으세요. (Postgres 플러그인 URL을 쓰면 안 됩니다.)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        normalize_database_url(raw)
    except ValueError as e:
        print(f"DATABASE_URL 형식 오류: {e}", file=sys.stderr)
        raise SystemExit(1) from e


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
        raw = database_url_effective()
        if not raw:
            raise RuntimeError("DATABASE_URL 또는 MYSQL_URL 이 설정되지 않았습니다.")
        url = normalize_database_url(raw)
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=280,
            echo=False,
            connect_args={
                "charset": "utf8mb4",
                "connect_timeout": 15,
            },
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
