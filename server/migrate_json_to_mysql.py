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

_SERVER = Path(__file__).resolve().parent
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))


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

    if not (os.environ.get("DATABASE_URL") or "").strip():
        print("오류: DATABASE_URL 환경 변수를 설정하세요.", file=sys.stderr)
        return 1

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
