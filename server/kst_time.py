"""한국 표준시(Asia/Seoul) 기준 날짜. 예약·당일 롤오버·DB 날짜 필드와 일치시킵니다."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def today_str_kst() -> str:
    return now_kst().strftime("%Y-%m-%d")


def today_date_kst() -> date:
    return now_kst().date()
