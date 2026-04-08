"""MySQL 저장소 (Railway DATABASE_URL). JSON 파일 폴백 없음."""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db_config import SessionLocal, get_engine, init_db
from db_models import (
    AccountRow,
    AppKvRow,
    BranchRow,
    DisplayContentLegacyRow,
    DisplayItemRow,
    DisplaySettingsRow,
    RoomsConfigRow,
    StaffReservationRow,
    StaffTodayLegacyRow,
    TelReservationRow,
    TelStoreLegacyRow,
)

JWT_KV_KEY = "jwt_secret"
_DEFAULT_BRANCH = "default"
TEL_LEGACY_ROW_ID = 1


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_ymd(s: str) -> date:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _session() -> Session:
    return SessionLocal()


def _safe_get(session: Session, model, key: Any) -> Any:
    """구버전 테이블이 없는 DB에서는 예외가 날 수 있음."""
    try:
        return session.get(model, key)
    except Exception:
        return None


def table_has_rows(model) -> bool:
    with _session() as s:
        return s.scalars(select(model).limit(1)).first() is not None


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


def load_branch_today(branch_id: str, *, _retry: bool = True) -> dict[str, Any]:
    """신규 테이블이 비어 있으면 구 `staff_today.payload_json` 에서 1회 이관."""
    legacy_data: Optional[dict[str, Any]] = None
    with _session() as s:
        q = (
            select(StaffReservationRow)
            .where(StaffReservationRow.branch_id == branch_id)
            .order_by(StaffReservationRow.sort_order, StaffReservationRow.id)
        )
        rows = s.execute(q).scalars().all()
        if rows:
            d0 = rows[0].date
            date_str = d0.isoformat() if isinstance(d0, date) else str(d0)
            reservations = []
            for r in rows:
                reservations.append(
                    {
                        "id": r.id,
                        "time": r.time,
                        "name": r.name,
                        "room": r.room,
                    }
                )
            return {"date": date_str, "reservations": reservations}
        if _retry:
            leg = _safe_get(s, StaffTodayLegacyRow, branch_id)
            if leg:
                try:
                    raw = json.loads(leg.payload_json)
                    if isinstance(raw, dict):
                        legacy_data = raw
                except json.JSONDecodeError:
                    pass

    if legacy_data is not None and _retry:
        save_branch_today(branch_id, legacy_data)
        with _session() as s2:
            leg2 = _safe_get(s2, StaffTodayLegacyRow, branch_id)
            if leg2:
                s2.delete(leg2)
                s2.commit()
        return load_branch_today(branch_id, _retry=False)

    return {"date": _today_str(), "reservations": []}


def save_branch_today(branch_id: str, data: dict[str, Any]) -> None:
    date_str = str(data.get("date") or _today_str())[:10]
    d = _parse_ymd(date_str)
    reservations = data.get("reservations") or []
    if not isinstance(reservations, list):
        reservations = []
    with _session() as s:
        s.execute(delete(StaffReservationRow).where(StaffReservationRow.branch_id == branch_id))
        for i, r in enumerate(reservations):
            if not isinstance(r, dict):
                continue
            s.add(
                StaffReservationRow(
                    branch_id=branch_id,
                    date=d,
                    time=str(r.get("time") or ""),
                    name=str(r.get("name") or ""),
                    room=str(r.get("room") or ""),
                    sort_order=i,
                )
            )
        s.commit()


def load_display_content(branch_id: str, *, _retry: bool = True) -> dict[str, Any]:
    """슬라이드가 없으면 구 `display_content.payload_json` 에서 1회 이관."""
    legacy_migrate: Optional[dict[str, Any]] = None
    st: Optional[DisplaySettingsRow] = None
    di = 8
    with _session() as s:
        st = s.get(DisplaySettingsRow, branch_id)
        di = int(st.default_interval_sec) if st else 8
        rows = (
            s.execute(
                select(DisplayItemRow)
                .where(DisplayItemRow.branch_id == branch_id)
                .order_by(DisplayItemRow.sort_order, DisplayItemRow.id)
            )
            .scalars()
            .all()
        )
        if rows:
            items: list[dict[str, Any]] = []
            for r in rows:
                it: dict[str, Any] = {
                    "id": str(r.id),
                    "type": r.type or "image",
                    "url": r.url or "",
                    "order": r.sort_order,
                }
                if (r.name or "").strip():
                    it["name"] = r.name
                if r.duration_sec is not None:
                    it["duration_sec"] = r.duration_sec
                items.append(it)
            return {"items": items, "default_interval_sec": di}
        if _retry:
            leg = _safe_get(s, DisplayContentLegacyRow, branch_id)
            if leg:
                try:
                    raw = json.loads(leg.payload_json)
                    if isinstance(raw, dict):
                        legacy_migrate = raw
                except json.JSONDecodeError:
                    pass

    if legacy_migrate is not None and _retry:
        save_display_content(branch_id, legacy_migrate)
        with _session() as s2:
            leg2 = _safe_get(s2, DisplayContentLegacyRow, branch_id)
            if leg2:
                s2.delete(leg2)
                s2.commit()
        return load_display_content(branch_id, _retry=False)

    if not st:
        return {"items": [], "default_interval_sec": 8}
    return {"items": [], "default_interval_sec": di}


def save_display_content(branch_id: str, data: dict[str, Any]) -> None:
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    try:
        di = int(data.get("default_interval_sec") or 8)
    except (TypeError, ValueError):
        di = 8
    with _session() as s:
        s.merge(DisplaySettingsRow(branch_id=branch_id, default_interval_sec=di))
        s.execute(delete(DisplayItemRow).where(DisplayItemRow.branch_id == branch_id))
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            url = str(it.get("url") or "")
            t = str(it.get("type") or "image").lower()
            if t not in ("video", "image"):
                t = "image"
            nm = str(it.get("name") or "")[:255]
            dur_raw = it.get("duration_sec")
            dur: Optional[int] = None
            if dur_raw is not None and str(dur_raw).strip() != "":
                try:
                    dur = int(dur_raw)
                except (TypeError, ValueError):
                    dur = None
            s.add(
                DisplayItemRow(
                    branch_id=branch_id,
                    sort_order=int(it.get("order") or i),
                    type=t,
                    url=url,
                    name=nm,
                    duration_sec=dur,
                )
            )
        s.commit()


def load_tel_store() -> dict[str, Any]:
    """신규 `tel_reservations` 가 비어 있으면 구 `tel_store` JSON 에서 1회 이관."""
    legacy_migrate: Optional[dict[str, Any]] = None
    with _session() as s:
        rows = s.execute(select(TelReservationRow).order_by(TelReservationRow.id)).scalars().all()
        if rows:
            out: list[dict[str, Any]] = []
            for r in rows:
                item: dict[str, Any] = {
                    "id": r.id,
                    "branch_id": r.branch_id,
                    "date": r.date,
                    "time": r.time,
                    "slot": r.slot,
                    "phone": r.phone,
                    "name": r.name,
                    "count": r.count,
                    "room": r.room,
                }
                if r.adult is not None:
                    item["adult"] = r.adult
                if r.child is not None:
                    item["child"] = r.child
                if r.infant is not None:
                    item["infant"] = r.infant
                out.append(item)
            return {"reservations": out}
        leg = _safe_get(s, TelStoreLegacyRow, TEL_LEGACY_ROW_ID)
        if leg:
            try:
                raw = json.loads(leg.payload_json)
                if isinstance(raw, dict):
                    legacy_migrate = raw
            except json.JSONDecodeError:
                pass

    if legacy_migrate is not None:
        items = legacy_migrate.get("reservations")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and "branch_id" not in it:
                    it["branch_id"] = _DEFAULT_BRANCH
        save_tel_store(legacy_migrate)
        with _session() as s2:
            leg2 = _safe_get(s2, TelStoreLegacyRow, TEL_LEGACY_ROW_ID)
            if leg2:
                s2.delete(leg2)
                s2.commit()
        return load_tel_store()

    return {"reservations": []}


def save_tel_store(data: dict[str, Any]) -> None:
    items = data.get("reservations") or []
    if not isinstance(items, list):
        items = []
    with _session() as s:
        s.execute(delete(TelReservationRow))
        for it in items:
            if not isinstance(it, dict):
                continue
            bid = str(it.get("branch_id") or _DEFAULT_BRANCH).strip().lower() or _DEFAULT_BRANCH
            row_kw: dict[str, Any] = {
                "branch_id": bid,
                "date": str(it.get("date") or "")[:10],
                "time": str(it.get("time") or ""),
                "slot": str(it.get("slot") or ""),
                "phone": str(it.get("phone") or ""),
                "name": str(it.get("name") or ""),
                "count": int(it.get("count") or 2),
                "room": str(it.get("room") or ""),
            }
            for k in ("adult", "child", "infant"):
                v = it.get(k)
                if v is None:
                    row_kw[k] = None
                else:
                    try:
                        row_kw[k] = int(v)
                    except (TypeError, ValueError):
                        row_kw[k] = None
            tid = it.get("id")
            if tid is not None:
                try:
                    iid = int(tid)
                    if iid > 0:
                        row_kw["id"] = iid
                except (TypeError, ValueError):
                    pass
            s.add(TelReservationRow(**row_kw))
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


def migrate_from_data_dir(data_dir: Path) -> bool:
    """DB가 비어 있을 때만 data/*.json 을 임포트. 이미 지점이 있으면 False."""
    init_db()
    from branch_data import DEFAULT_BRANCH_ID

    with _session() as s:
        if s.scalars(select(BranchRow).limit(1)).first() is not None:
            return False

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
    if not table_has_rows(TelReservationRow):
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
        if not table_has_rows(TelReservationRow):
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

    return True


def seed_new_branch(branch_id: str, name: str) -> None:
    save_branch_today(branch_id, {"date": _today_str(), "reservations": []})
    save_display_content(branch_id, {"items": [], "default_interval_sec": 8})
