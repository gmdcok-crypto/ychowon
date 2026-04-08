"""MySQL/MariaDB 연결.

런타임 저장소는 **MySQL만** 사용합니다. ``DATABASE_URL`` 등이 없으면 기동하지 않습니다.
(구 ``data/*.json`` 은 ``migrate_from_data_dir`` / ``migrate_json_to_mysql.py`` 로 DB 이전할 때만 읽습니다.)

Railway MySQL은 웹 서비스에 ``DATABASE_URL`` 대신 ``MYSQL_URL`` 만 노출되는 경우가 있어 둘 다 지원합니다.

**지점별 DB 완전 분리 (mchowon / ychowon 등)**  
한 MySQL을 두 웹 서비스가 같이 쓰지 말고, **웹 서비스마다 MySQL 플러그인을 따로** 두세요.
각 웹 서비스 Variables에는 **그 MySQL 하나**의 ``DATABASE_URL``(또는 ``${{MySQL.MYSQL_URL}}``)만 연결합니다.
그러면 스키마·예약·지점·컨텐츠가 서로 섞이지 않습니다. (``DEFAULT_BRANCH_ID`` 는 같은 DB를 쓸 때의 보조용)
"""

from __future__ import annotations

import os
import sys
from typing import Optional
from urllib.parse import quote_plus, urlparse

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


def mysql_target_summary() -> str:
    """로그용: 연결 대상 호스트·포트·DB 이름 (비밀번호 제외)."""
    raw = database_url_effective()
    if not raw:
        return ""
    try:
        if not raw.startswith(("mysql://", "mysql+pymysql://")):
            return "(MySQL URL 아님)"
        p = urlparse(raw)
        host = p.hostname or "?"
        port = p.port or 3306
        db = (p.path or "").lstrip("/").split("?")[0] or "?"
        return f"{host}:{port}/{db}"
    except Exception:
        return "(URL 요약 실패)"


def running_on_railway() -> bool:
    """Railway 컨테이너에서 실행 중인지 (배포·railway run 등)."""
    return bool((os.environ.get("RAILWAY_ENVIRONMENT") or "").strip())


def database_enabled() -> bool:
    """DB 저장소 사용 여부. 연결 문자열이 있을 때만 True (JSON 폴백 없음)."""
    return bool(database_url_effective())


def ensure_database_url_or_exit() -> None:
    """MySQL 연결 문자열이 없으면 프로세스 종료 (로컬·Railway 공통)."""
    if database_url_effective():
        return
    print(
        "오류: MySQL 연결 정보가 필요합니다. JSON 파일 저장은 런타임에 사용하지 않습니다.\n"
        "  · DATABASE_URL 또는 MYSQL_URL\n"
        "  · 또는 MYSQLHOST, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE (및 MYSQLPORT)\n"
        "Railway: MySQL 서비스를 웹 서비스 Variables에 연결 (예: ${{MySQL.MYSQL_URL}})\n"
        "로컬: Docker MySQL 등에 연결하거나 migrate_json_to_mysql.py 로 이전 후 사용하세요.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def ensure_railway_database_url_or_exit() -> None:
    """호환용 별칭. ``ensure_database_url_or_exit`` 와 동일."""
    ensure_database_url_or_exit()


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


def _ensure_staff_reservation_party_columns() -> None:
    """기존 DB에 staff_reservations 인원 컬럼이 없으면 추가 (create_all 은 컬럼 추가를 안 함)."""
    from sqlalchemy import inspect, text

    eng = get_engine()
    insp = inspect(eng)
    try:
        if not insp.has_table("staff_reservations"):
            return
    except Exception:
        return
    try:
        cols = {c["name"] for c in insp.get_columns("staff_reservations")}
    except Exception:
        return
    alters: list[str] = []
    if "count" not in cols:
        alters.append(
            "ALTER TABLE staff_reservations ADD COLUMN count INT NOT NULL DEFAULT 2"
        )
    if "adult" not in cols:
        alters.append("ALTER TABLE staff_reservations ADD COLUMN adult INT NULL")
    if "child" not in cols:
        alters.append("ALTER TABLE staff_reservations ADD COLUMN child INT NULL")
    if "infant" not in cols:
        alters.append("ALTER TABLE staff_reservations ADD COLUMN infant INT NULL")
    if not alters:
        return
    with eng.begin() as conn:
        for sql in alters:
            conn.execute(text(sql))


def init_db() -> None:
    from db_models import Base

    Base.metadata.create_all(bind=get_engine())
    _ensure_staff_reservation_party_columns()
