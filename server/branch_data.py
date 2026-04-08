"""
지점(branch)별 당일 예약·현황판 하단 광고. 저장소는 MySQL (db_repo)만 사용.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

BRANCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DEFAULT_BRANCH_ID = "default"

_ROOT: Optional[Path] = None


def configure(data_dir: Path) -> None:
    global _ROOT
    _ROOT = data_dir


def _root() -> Path:
    if _ROOT is None:
        raise RuntimeError("branch_data.configure() not called")
    return _ROOT


def branches_path() -> Path:
    return _root() / "branches.json"


def today_dir() -> Path:
    return _root() / "today"


def display_content_dir() -> Path:
    return _root() / "display_content"


def legacy_today_file() -> Path:
    return _root() / "today.json"


def legacy_display_file() -> Path:
    return _root() / "display_content.json"


def today_path(branch_id: str) -> Path:
    return today_dir() / f"{branch_id}.json"


def display_content_path(branch_id: str) -> Path:
    return display_content_dir() / f"{branch_id}.json"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_branches() -> list[dict[str, Any]]:
    from db_repo import load_branches as db_load_branches

    rows = db_load_branches()
    out = []
    for r in rows:
        bid = str(r.get("id") or "").strip().lower()
        if not BRANCH_ID_RE.match(bid):
            continue
        name = str(r.get("name") or bid).strip()[:80] or bid
        out.append({"id": bid, "name": name})
    return out if out else [{"id": DEFAULT_BRANCH_ID, "name": "본점"}]


def branch_ids() -> set[str]:
    return {b["id"] for b in load_branches()}


def normalize_branch_id(branch: Optional[str]) -> str:
    b = (branch or DEFAULT_BRANCH_ID).strip().lower()
    if not BRANCH_ID_RE.match(b):
        raise HTTPException(status_code=400, detail="잘못된 지점 코드입니다.")
    if b not in branch_ids():
        raise HTTPException(status_code=400, detail=f"등록되지 않은 지점입니다: {b}")
    return b


def tel_branch_key(item: dict) -> str:
    return str(item.get("branch_id") or DEFAULT_BRANCH_ID).strip().lower() or DEFAULT_BRANCH_ID


def load_branch_today(branch_id: str) -> dict:
    from db_repo import load_branch_today as db_load

    return db_load(branch_id)


def save_branch_today(branch_id: str, data: dict) -> None:
    from db_repo import save_branch_today as db_save

    db_save(branch_id, data)


def load_display_content(branch_id: str) -> dict:
    from db_repo import load_display_content as db_load

    return db_load(branch_id)


def save_display_content(branch_id: str, data: dict) -> None:
    from db_repo import save_display_content as db_save

    db_save(branch_id, data)


def append_branch(branch_id: str, name: str) -> None:
    bid = branch_id.strip().lower()
    if not BRANCH_ID_RE.match(bid):
        raise ValueError("지점 코드는 영문 소문자·숫자로 시작하고, 소문자·숫자·_- 만 32자 이내로 입력하세요.")
    rows = load_branches()
    if any(b["id"] == bid for b in rows):
        raise ValueError("이미 있는 지점 코드입니다.")
    rows.append({"id": bid, "name": (name or bid).strip()[:80] or bid})
    from db_repo import replace_branches, seed_new_branch

    replace_branches(rows)
    seed_new_branch(bid, (name or bid).strip()[:80] or bid)
