"""
지점(branch)별 당일 예약·현황판 하단 광고.

런타임 저장은 MySQL(db_repo)만 사용합니다. 아래 파일 경로·ensure_migrations 는
구 데이터 이전·마이그레이션 스크립트용으로만 남아 있습니다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from kst_time import today_str_kst

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
    return today_str_kst()


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


def _strip_host_port(host: str) -> str:
    h = (host or "").strip().lower()
    if not h:
        return ""
    if h.startswith("["):
        return h.split("]", 1)[0] + "]" if "]" in h else h
    if ":" in h:
        return h.rsplit(":", 1)[0]
    return h


def _deployment_hint_blob(host: Optional[str]) -> str:
    """Host + Railway 공개 도메인·서비스명 등에서 mchowon/ychowon 문자열 탐지."""
    parts: list[str] = []
    sh = _strip_host_port(host or "")
    if sh:
        parts.append(sh)
    for key in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_SERVICE_NAME", "RAILWAY_PROJECT_NAME"):
        v = (os.environ.get(key) or "").strip()
        if not v:
            continue
        v = v.lower()
        if "://" in v:
            v = v.split("://", 1)[-1]
        v = v.split("/")[0]
        if ":" in v and not v.startswith("["):
            v = v.rsplit(":", 1)[0]
        parts.append(v)
    return " ".join(parts)


def infer_branch_from_host(host: Optional[str]) -> Optional[str]:
    """Host 헤더·Railway 환경 변수 문자열에 ychowon/mchowon 이 포함되면 해당 지점."""
    t = _deployment_hint_blob(host)
    if "ychowon" in t:
        return "ychowon"
    if "mchowon" in t:
        return "mchowon"
    return None


def railway_service_branch_hint(ids: set[str]) -> Optional[str]:
    """Railway 서비스 이름이 branches 의 id 와 동일한 경우 (예: RAILWAY_SERVICE_NAME=mchowon)."""
    v = (os.environ.get("RAILWAY_SERVICE_NAME") or "").strip().lower()
    if v and v in ids:
        return v
    return None


def resolve_effective_branch(branch: Optional[str], host: Optional[str]) -> str:
    """
    클라이언트가 branch=default 로 보낼 때:
    - DEFAULT_BRANCH_ID·Host·Railway 도메인/서비스명으로 특정 지점이 잡히면 그 지점을 씀
      (DB에 default 행이 있어도, 같은 DB를 쓰는 두 Railway 배포를 나누기 위해)
    - 그렇지 않으면 등록된 default 지점을 씀.
    """
    b = (branch or DEFAULT_BRANCH_ID).strip().lower() or DEFAULT_BRANCH_ID
    ids = branch_ids()

    if b != DEFAULT_BRANCH_ID:
        return normalize_branch_id(b)

    env_b = deployment_default_branch_id()
    ordered: list[str] = []
    if env_b and env_b in ids:
        ordered.append(env_b)
    h = infer_branch_from_host(host)
    if h and h in ids:
        ordered.append(h)
    svc = railway_service_branch_hint(ids)
    if svc and svc in ids:
        ordered.append(svc)

    seen: set[str] = set()
    deduped: list[str] = []
    for x in ordered:
        if x not in seen:
            seen.add(x)
            deduped.append(x)

    if DEFAULT_BRANCH_ID not in ids:
        for c in deduped:
            return normalize_branch_id(c)
        raise HTTPException(
            status_code=400,
            detail="등록된 지점이 없거나 default 를 결정할 수 없습니다. branches·DEFAULT_BRANCH_ID 를 확인하세요.",
        )

    for c in deduped:
        if c != DEFAULT_BRANCH_ID:
            return normalize_branch_id(c)

    return normalize_branch_id(DEFAULT_BRANCH_ID)


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
        return {"items": [], "default_interval_sec": 8, "top_items": [], "top_default_interval_sec": 8}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                if not isinstance(data.get("top_items"), list):
                    data["top_items"] = []
                try:
                    data["top_default_interval_sec"] = int(data.get("top_default_interval_sec") or 8)
                except (TypeError, ValueError):
                    data["top_default_interval_sec"] = 8
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"items": [], "default_interval_sec": 8, "top_items": [], "top_default_interval_sec": 8}


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
    save_display_content(bid, {"items": [], "default_interval_sec": 8, "top_items": [], "top_default_interval_sec": 8})
