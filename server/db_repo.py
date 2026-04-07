"""DATABASE_URL 사용 시 JSON 파일 대신 MySQL 저장."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db_config import SessionLocal, get_engine, init_db
from db_models import (
    AccountRow,
    AppKvRow,
    BranchRow,
    DisplayContentRow,
    RoomsConfigRow,
    StaffTodayRow,
    TelStoreRow,
)

TEL_STORE_ID = 1
JWT_KV_KEY = "jwt_secret"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _session() -> Session:
    return SessionLocal()


def table_has_rows(model) -> bool:
    with _session() as s:
        n = s.execute(select(func.count()).select_from(model)).scalar()
        return bool(n and n > 0)


def load_auth_store() -> dict[str, Any]:
    with _session() as s:
        rows = s.execute(select(AccountRow).order_by(AccountRow.id)).scalars().all()
        accs = []
        for r in rows:
            accs.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "role": r.role,
                    "password_hash": r.password_hash,
                }
            )
        return {"accounts": accs}


def save_auth_store(data: dict[str, Any]) -> None:
    accs = data.get("accounts")
    if not isinstance(accs, list):
        return
    with _session() as s:
        s.execute(delete(AccountRow))
        for a in accs:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "").strip()
            if not aid:
                continue
            s.add(
                AccountRow(
                    id=aid,
                    name=str(a.get("name") or ""),
                    role=str(a.get("role") or ""),
                    password_hash=a.get("password_hash") if isinstance(a.get("password_hash"), (str, type(None))) else None,
                )
            )
        s.commit()


def get_or_create_jwt_secret() -> str:
    with _session() as s:
        row = s.get(AppKvRow, JWT_KV_KEY)
        if row and row.v.strip():
            return row.v.strip()
        sec = secrets.token_hex(32)
        s.merge(AppKvRow(k=JWT_KV_KEY, v=sec))
        s.commit()
        return sec


def set_jwt_secret_db(value: str) -> None:
    with _session() as s:
        s.merge(AppKvRow(k=JWT_KV_KEY, v=value))
        s.commit()


def load_branches() -> list[dict[str, Any]]:
    with _session() as s:
        rows = s.execute(select(BranchRow).order_by(BranchRow.id)).scalars().all()
        return [{"id": r.id, "name": r.name} for r in rows]


def replace_branches(rows: list[dict[str, Any]]) -> None:
    with _session() as s:
        s.execute(delete(BranchRow))
        for b in rows:
            bid = str(b.get("id") or "").strip().lower()
            if not bid:
                continue
            s.add(BranchRow(id=bid, name=str(b.get("name") or bid)[:80]))
        s.commit()


def load_branch_today(branch_id: str) -> dict[str, Any]:
    with _session() as s:
        row = s.get(StaffTodayRow, branch_id)
        if not row:
            return {"date": _today_str(), "reservations": []}
        try:
            d = json.loads(row.payload_json)
            return d if isinstance(d, dict) else {"date": _today_str(), "reservations": []}
        except json.JSONDecodeError:
            return {"date": _today_str(), "reservations": []}


def save_branch_today(branch_id: str, data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with _session() as s:
        s.merge(StaffTodayRow(branch_id=branch_id, payload_json=payload))
        s.commit()


def load_display_content(branch_id: str) -> dict[str, Any]:
    with _session() as s:
        row = s.get(DisplayContentRow, branch_id)
        if not row:
            return {"items": [], "default_interval_sec": 8}
        try:
            d = json.loads(row.payload_json)
            return d if isinstance(d, dict) else {"items": [], "default_interval_sec": 8}
        except json.JSONDecodeError:
            return {"items": [], "default_interval_sec": 8}


def save_display_content(branch_id: str, data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with _session() as s:
        s.merge(DisplayContentRow(branch_id=branch_id, payload_json=payload))
        s.commit()


def load_tel_store() -> dict[str, Any]:
    with _session() as s:
        row = s.get(TelStoreRow, TEL_STORE_ID)
        if not row:
            return {"reservations": []}
        try:
            d = json.loads(row.payload_json)
            return d if isinstance(d, dict) else {"reservations": []}
        except json.JSONDecodeError:
            return {"reservations": []}


def save_tel_store(data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with _session() as s:
        s.merge(TelStoreRow(id=TEL_STORE_ID, payload_json=payload))
        s.commit()


def load_rooms_config_file(file_name: str) -> Optional[dict[str, Any]]:
    with _session() as s:
        row = s.get(RoomsConfigRow, file_name)
        if not row:
            return None
        try:
            d = json.loads(row.payload_json)
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None


def save_rooms_config_file(file_name: str, data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with _session() as s:
        s.merge(RoomsConfigRow(file_name=file_name, payload_json=payload))
        s.commit()


def migrate_from_data_dir(data_dir: Path) -> None:
    """DB가 비어 있을 때만 data/*.json 을 임포트."""
    init_db()
    from branch_data import DEFAULT_BRANCH_ID

    with _session() as s:
        if s.scalars(select(BranchRow).limit(1)).first() is not None:
            return

    # branches.json
    bp = data_dir / "branches.json"
    if bp.is_file():
        try:
            raw = json.loads(bp.read_text(encoding="utf-8"))
            rows = raw.get("branches") if isinstance(raw, dict) else None
            if isinstance(rows, list) and rows:
                out = []
                for r in rows:
                    if isinstance(r, dict):
                        bid = str(r.get("id") or "").strip().lower()
                        if bid:
                            out.append({"id": bid, "name": str(r.get("name") or bid)})
                if out:
                    replace_branches(out)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    if not table_has_rows(BranchRow):
        replace_branches([{"id": DEFAULT_BRANCH_ID, "name": "본점"}])

    # auth.json
    if not table_has_rows(AccountRow):
        ap = data_dir / "auth.json"
        if ap.is_file():
            try:
                raw = json.loads(ap.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("accounts"):
                    save_auth_store(raw)
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        if not table_has_rows(AccountRow):
            save_auth_store(
                {
                    "accounts": [
                        {"id": "admin", "name": "관리자", "role": "admin", "password_hash": None},
                        {"id": "display", "name": "현황판", "role": "display", "password_hash": None},
                        {"id": "tel", "name": "전화예약", "role": "tel", "password_hash": None},
                    ]
                }
            )

    # jwt secret file
    sf = data_dir / ".jwt_secret"
    if sf.is_file():
        try:
            sec = sf.read_text(encoding="utf-8").strip()
            if sec:
                set_jwt_secret_db(sec)
        except OSError:
            pass

    # staff today per branch
    td = data_dir / "today"
    if td.is_dir():
        for p in td.glob("*.json"):
            bid = p.stem
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    save_branch_today(bid, data)
            except (OSError, json.JSONDecodeError):
                pass
    leg = data_dir / "today.json"
    if leg.is_file():
        try:
            data = json.loads(leg.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                save_branch_today(DEFAULT_BRANCH_ID, data)
        except (OSError, json.JSONDecodeError):
            pass

    # display_content
    dd = data_dir / "display_content"
    if dd.is_dir():
        for p in dd.glob("*.json"):
            bid = p.stem
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    save_display_content(bid, data)
            except (OSError, json.JSONDecodeError):
                pass
    dg = data_dir / "display_content.json"
    if dg.is_file():
        try:
            data = json.loads(dg.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                save_display_content(DEFAULT_BRANCH_ID, data)
        except (OSError, json.JSONDecodeError):
            pass

    # tel (+ branch_id 보강, ensure_migrations 와 동일)
    if not table_has_rows(TelStoreRow):
        tp = data_dir / "tel_reservations.json"
        if tp.is_file():
            try:
                data = json.loads(tp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    items = data.get("reservations")
                    if isinstance(items, list):
                        for it in items:
                            if isinstance(it, dict) and "branch_id" not in it:
                                it["branch_id"] = DEFAULT_BRANCH_ID
                    save_tel_store(data)
            except (OSError, json.JSONDecodeError):
                pass
        if not table_has_rows(TelStoreRow):
            save_tel_store({"reservations": []})

    # rooms_config *.json
    for name in (
        "rooms_config.json",
        "rooms_config.mchowon.json",
        "rooms_config.example.json",
    ):
        rp = data_dir / name
        if rp.is_file():
            try:
                data = json.loads(rp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    save_rooms_config_file(name, data)
            except (OSError, json.JSONDecodeError):
                pass


def seed_new_branch(branch_id: str, name: str) -> None:
    save_branch_today(branch_id, {"date": _today_str(), "reservations": []})
    save_display_content(branch_id, {"items": [], "default_interval_sec": 8})
