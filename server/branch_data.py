"""
지점(branch)별 당일 예약·현황판 하단 광고 JSON.
기존 단일 파일(today.json, display_content.json)은 최초 기동 시 default 지점으로 이관합니다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

BRANCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DEFAULT_BRANCH_ID = "default"

_ROOT: Optional[Path] = None


def _use_db() -> bool:
    try:
        from db_config import database_enabled

        return database_enabled()
    except Exception:
        return False


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
    if _use_db():
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


def deployment_default_branch_id() -> Optional[str]:
    v = (os.environ.get("DEFAULT_BRANCH_ID") or "").strip().lower()
    if v and BRANCH_ID_RE.match(v):
        return v
    return None


def infer_branch_from_host(host: Optional[str]) -> Optional[str]:
    """Railway 등 호스트명에 서비스명이 들어간 경우 (예: mchowon-production-....up.railway.app)."""
    h = (host or "").strip().lower()
    if ":" in h:
        h = h.split(":")[0]
    if "ychowon" in h:
        return "ychowon"
    if "mchowon" in h:
        return "mchowon"
    return None


def railway_service_branch_hint(ids: set[str]) -> Optional[str]:
    """Railway 서비스 이름을 지점 코드와 동일하게 둔 경우 (예: RAILWAY_SERVICE_NAME=mchowon)."""
    v = (os.environ.get("RAILWAY_SERVICE_NAME") or "").strip().lower()
    if v and v in ids:
        return v
    return None


def resolve_effective_branch(branch: Optional[str], host: Optional[str]) -> str:
    """
    클라이언트가 branch=default 로 보낼 때, DB에 literal default 지점이 없으면
    이 배포의 DEFAULT_BRANCH_ID, Host 헤더, Railway 서비스명으로 실제 지점을 고릅니다.
    (현황판·전화예약이 쿼리 없이 열릴 때 지점이 갈리도록)
    """
    b = (branch or DEFAULT_BRANCH_ID).strip().lower() or DEFAULT_BRANCH_ID
    ids = branch_ids()
    if b == DEFAULT_BRANCH_ID and DEFAULT_BRANCH_ID not in ids:
        for candidate in (
            deployment_default_branch_id(),
            infer_branch_from_host(host),
            railway_service_branch_hint(ids),
        ):
            if candidate and candidate in ids:
                b = candidate
                break
    return normalize_branch_id(b)


def tel_branch_key(item: dict) -> str:
    return str(item.get("branch_id") or DEFAULT_BRANCH_ID).strip().lower() or DEFAULT_BRANCH_ID


def load_branch_today(branch_id: str) -> dict:
    if _use_db():
        from db_repo import load_branch_today as db_load

        return db_load(branch_id)

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
    if _use_db():
        from db_repo import save_branch_today as db_save

        db_save(branch_id, data)
        return

    today_dir().mkdir(parents=True, exist_ok=True)
    p = today_path(branch_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_display_content(branch_id: str) -> dict:
    if _use_db():
        from db_repo import load_display_content as db_load

        return db_load(branch_id)

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
    if _use_db():
        from db_repo import save_display_content as db_save

        db_save(branch_id, data)
        return

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
    if _use_db():
        from db_repo import replace_branches, seed_new_branch

        replace_branches(rows)
        seed_new_branch(bid, (name or bid).strip()[:80] or bid)
        return

    branches_path().write_text(
        json.dumps({"branches": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_branch_today(bid, {"date": today_str(), "reservations": []})
    save_display_content(bid, {"items": [], "default_interval_sec": 8})
