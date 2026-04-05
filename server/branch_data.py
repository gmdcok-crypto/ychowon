"""
지점(branch)별 당일 예약·현황판 하단 광고 JSON.
기존 단일 파일(today.json, display_content.json)은 최초 기동 시 default 지점으로 이관합니다.
"""
from __future__ import annotations

import json
import re
import shutil
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


def ensure_migrations(tel_file: Path) -> None:
    """최초 1회: branches.json, today/, display_content/, tel branch_id 보강."""
    data_dir = _root()
    data_dir.mkdir(parents=True, exist_ok=True)
    today_dir().mkdir(parents=True, exist_ok=True)
    display_content_dir().mkdir(parents=True, exist_ok=True)

    bp = branches_path()
    if not bp.exists():
        bp.write_text(
            json.dumps(
                {"branches": [{"id": DEFAULT_BRANCH_ID, "name": "본점"}]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    leg = legacy_today_file()
    dest = today_path(DEFAULT_BRANCH_ID)
    if leg.is_file() and not dest.exists():
        try:
            shutil.copy2(leg, dest)
        except OSError:
            pass

    leg_d = legacy_display_file()
    dest_d = display_content_path(DEFAULT_BRANCH_ID)
    if leg_d.is_file() and not dest_d.exists():
        try:
            shutil.copy2(leg_d, dest_d)
        except OSError:
            pass

    # tel_reservations.json 에 branch_id 없으면 default
    if tel_file.is_file():
        try:
            raw = json.loads(tel_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = None
        if isinstance(raw, dict):
            items = raw.get("reservations")
            if isinstance(items, list):
                changed = False
                for it in items:
                    if isinstance(it, dict) and "branch_id" not in it:
                        it["branch_id"] = DEFAULT_BRANCH_ID
                        changed = True
                if changed:
                    try:
                        tel_file.write_text(
                            json.dumps(raw, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except OSError:
                        pass


def load_branches() -> list[dict[str, Any]]:
    p = branches_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("branches")
        if isinstance(rows, list) and rows:
            out = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                bid = str(r.get("id") or "").strip().lower()
                if not BRANCH_ID_RE.match(bid):
                    continue
                name = str(r.get("name") or bid).strip()[:80] or bid
                out.append({"id": bid, "name": name})
            if out:
                return out
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return [{"id": DEFAULT_BRANCH_ID, "name": "본점"}]


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
    p = today_path(branch_id)
    if not p.exists():
        return {"date": today_str(), "reservations": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"date": today_str(), "reservations": []}


def save_branch_today(branch_id: str, data: dict) -> None:
    today_dir().mkdir(parents=True, exist_ok=True)
    p = today_path(branch_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_display_content(branch_id: str) -> dict:
    p = display_content_path(branch_id)
    if not p.exists():
        return {"items": [], "default_interval_sec": 8}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"items": [], "default_interval_sec": 8}


def save_display_content(branch_id: str, data: dict) -> None:
    display_content_dir().mkdir(parents=True, exist_ok=True)
    p = display_content_path(branch_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_branch(branch_id: str, name: str) -> None:
    bid = branch_id.strip().lower()
    if not BRANCH_ID_RE.match(bid):
        raise ValueError("지점 코드는 영문 소문자·숫자로 시작하고, 소문자·숫자·_- 만 32자 이내로 입력하세요.")
    rows = load_branches()
    if any(b["id"] == bid for b in rows):
        raise ValueError("이미 있는 지점 코드입니다.")
    rows.append({"id": bid, "name": (name or bid).strip()[:80] or bid})
    branches_path().write_text(
        json.dumps({"branches": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 빈 당일·빈 광고
    save_branch_today(bid, {"date": today_str(), "reservations": []})
    save_display_content(bid, {"items": [], "default_interval_sec": 8})
