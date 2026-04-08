#!/usr/bin/env python3
"""
server/data/*.json → MySQL/MariaDB 마이그레이션 (일회성).

비밀번호·URL은 코드에 넣지 말고 환경 변수만 사용하세요.

  Windows (PowerShell):
    $env:DATABASE_URL="mysql://USER:PASSWORD@HOST:3306/railway"
    cd server
    python migrate_json_to_mysql.py

  --force : 기존 테이블을 모두 지운 뒤 다시 임포트 (데이터 삭제됨)

연결 주의:
  - mysql.railway.internal 은 Railway 네트워크 안에서만 됩니다.
  - 로컬 PC에서 돌리려면 Railway MySQL 화면의 Public TCP/프록시 URL을 쓰거나,
    `railway run python migrate_json_to_mysql.py` 처럼 Railway 안에서 실행하세요.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_SERVER = Path(__file__).resolve().parent
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from db_config import database_url_effective  # noqa: E402


def _fail_if_local_railway_internal() -> Optional[int]:
    """
    mysql.railway.internal 은 Railway 컨테이너 안에서만 이름이 풀립니다.
    로컬 PC에서 쓰면 getaddrinfo failed(11001) 가 납니다.
    """
    raw = database_url_effective()
    if not raw:
        return None
    norm = raw
    if norm.startswith("mysql+pymysql://"):
        norm = "mysql://" + norm[len("mysql+pymysql://") :]
    u = urlparse(norm)
    host = (u.hostname or "").lower()
    if "railway.internal" not in host:
        return None
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("ALLOW_RAILWAY_INTERNAL_LOCAL"):
        return None
    print(
        "오류: DATABASE_URL 의 호스트가 mysql.railway.internal 입니다.\n"
        "이 주소는 집/로컬 PC에서는 DNS가 안 풀립니다 (지금 난 getaddrinfo failed).\n\n"
        "선택지:\n"
        "  1) Railway → MySQL 서비스 → Networking / Variables 에서 나오는\n"
        "     공개(Public) 호스트·포트로 URL을 바꿔 $env:DATABASE_URL 에 넣기\n"
        "  2) Railway CLI:  railway run --service <웹서비스이름> python migrate_json_to_mysql.py\n"
        "     (같은 프로젝트 네트워크 안에서 실행)\n"
        "  3) 마이그레이션을 로컬에서 안 하고, 배포된 앱이 빈 DB에 자동 임포트하게 두기\n\n"
        "고급: 정말 로컬에서 internal 을 써야 하면 ALLOW_RAILWAY_INTERNAL_LOCAL=1",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="JSON(data/) → MySQL 마이그레이션")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=_SERVER / "data",
        help="JSON 루트 (기본: server/data)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="기존 DB 테이블 삭제 후 전체 임포트 (주의: DB 데이터 삭제)",
    )
    args = ap.parse_args()

    if not database_url_effective():
        print("오류: DATABASE_URL 또는 MYSQL_URL 환경 변수를 설정하세요.", file=sys.stderr)
        return 1

    early = _fail_if_local_railway_internal()
    if early is not None:
        return early

    from db_config import database_enabled, get_engine, init_db
    from db_models import Base
    from db_repo import migrate_from_data_dir

    if not database_enabled():
        print("오류: DATABASE_URL 형식을 확인하세요 (mysql://...)", file=sys.stderr)
        return 1

    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"오류: 디렉터리 없음: {data_dir}", file=sys.stderr)
        return 1

    if args.force:
        print("기존 테이블 삭제 후 재생성 (--force) …")
        engine = get_engine()
        Base.metadata.drop_all(bind=engine)
        init_db()

    imported = migrate_from_data_dir(data_dir)
    if not imported:
        print(
            "스킵: DB에 이미 지점(branches) 데이터가 있습니다. "
            "덮어쓰려면 --force 로 다시 실행하세요.",
            file=sys.stderr,
        )
        return 2

    print("마이그레이션 완료:", data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
