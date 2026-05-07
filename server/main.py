"""
초원농원 예약 현황판 — 당일·예약 데이터는 MySQL, 날짜 기준은 한국시간(KST)

로그·Invalid HTTP request 관련 (참고):
- favicon /sw.js 404 는 아래 고정 라우트로 완화.
- Invalid HTTP request 는 보통 HTTPS를 HTTP 포트로 보내거나 스캐너·봇이 섞인 요청이라
  앱으로는 차단 불가. 개발 시 --host 127.0.0.1 만 열기, 운영 시 방화벽·VPN·
  nginx/Caddy 리버스 프록시(TLS 종료) 뒤에 두면 노이즈가 줄어듦.
- 콘솔을 덜 시끄럽게: uvicorn --log-level warning (또는 error)
"""
import asyncio
import json
import os
import socket
import sys
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

app = FastAPI(title="초원농원 예약 현황 API")

ws_by_branch: dict[str, set[WebSocket]] = defaultdict(set)
DISPLAY_BUILD_VERSION = (
    (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "").strip()
    or (os.environ.get("RAILWAY_DEPLOYMENT_ID") or "").strip()
    or str(int(time.time()))
)


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.on_event("startup")
def startup():
    import sys
    ip = _local_ip()
    print("")
    print("  예약 현황판 서버 실행 중")
    print("  Python:   %s" % sys.executable)
    print("  로컬:     http://127.0.0.1:8000")
    print("  네트워크: http://%s:8000" % ip)
    print("  현황판:   http://%s:8000/display/" % ip)
    print("  예약입력: http://%s:8000/admin/ (당일용)" % ip)
    print("  예약접수: http://%s:8000/tel/   (태블릿)" % ip)
    print("  Print:     http://%s:8000/print/ (POS)" % ip)
    from room_config import ACTIVE_ROOMS_CONFIG_REF as _room_cfg_ref

    if _room_cfg_ref:
        print("  룸·홀:    MySQL — %s" % _room_cfg_ref)
    else:
        print("  룸·홀:    내장 기본값 (ROOMS_CONFIG_FILE 또는 data/%s)" % CONFIG_FILENAME)
    try:
        from db_config import mysql_target_summary

        _tgt = mysql_target_summary()
    except Exception:
        _tgt = ""
    _suffix = (" → " + _tgt) if _tgt else ""
    if running_on_railway():
        print("  저장소:   Railway MySQL (지점별로 DB 따로 연결 권장)%s" % _suffix)
    else:
        print("  저장소:   MySQL/MariaDB%s" % _suffix)
    try:
        from r2_storage import r2_enabled

        if r2_enabled():
            print("  하단광고 업로드: Cloudflare R2 (필수)")
        else:
            print("  하단광고 업로드: R2 미설정 — /api/display/upload 는 503 (환경 변수 필요)")
    except Exception:
        print("  하단광고 업로드: R2 설정 확인 불가 — 업로드 API 사용 불가")
    print("")


# 루트에서 자주 요청됨 — 404 한 줄·브라우저 재시도 감소
_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#1a1510"/>'
    '<circle cx="16" cy="16" r="7" fill="#c9a962"/></svg>'
)
_SW_JS_NOOP = (
    b"// root noop SW\n"
    b"self.addEventListener('install',function(e){self.skipWaiting();});\n"
    b"self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim());});\n"
)


@app.get("/favicon.ico")
def favicon():
    return Response(content=_FAVICON_SVG.encode("utf-8"), media_type="image/svg+xml")


@app.get("/sw.js")
def service_worker_root():
    return Response(
        content=_SW_JS_NOOP,
        media_type="application/javascript; charset=utf-8",
    )


@app.get("/")
def root():
    return RedirectResponse(url="/display/")


@app.get("/print")
def print_redirect():
    """Redirect /print to the print screen."""
    return RedirectResponse(url="/print/")


@app.get("/display")
def display_redirect():
    """끝에 슬래시 없이 /display 로 접속해도 현황판으로."""
    return RedirectResponse(url="/display/")

# 현황판·관리자·태블릿 정적 경로 (app.mount 는 파일 맨 아래에서 등록 — /api 라우트가 먼저 매칭되도록)
DISPLAY_DIR = Path(__file__).resolve().parent.parent / "display"
ADMIN_DIR = Path(__file__).resolve().parent.parent / "admin"
TEL_DIR = Path(__file__).resolve().parent.parent / "tel"
PRINT_DIR = Path(__file__).resolve().parent.parent / "print"

# 모바일 → 예약 접수 화면으로
@app.get("/mobile")
@app.get("/mobile/")
def mobile_redirect():
    return RedirectResponse(url="/tel/")

# CORS (다른 포트에서 띄운 화면에서 API 호출 시)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _auth_middleware_layer(request: Request, call_next):
    return await auth_middleware(request, call_next)


_NO_STORE_PATHS = {
    "/display",
    "/display/",
    "/display/index.html",
    "/display/sw.js",
    "/admin",
    "/admin/",
    "/admin/index.html",
    "/admin/all.html",
    "/admin/display-content.html",
    "/admin/login.html",
    "/tel",
    "/tel/",
    "/tel/index.html",
    "/tel/login.html",
    "/tel/sw.js",
    "/print",
    "/print/",
    "/print/index.html",
    "/print/login.html",
}


@app.middleware("http")
async def _entrypoint_cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in _NO_STORE_PATHS:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# 당일 예약 저장 파일 (DB 대신 단일 JSON)
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

from auth_service import (
    ROLES,
    account_branch_from_payload,
    account_create,
    account_delete,
    account_revoke,
    account_update,
    auth_cookie_response,
    branch_allows_request,
    auth_middleware,
    configure as auth_configure,
    create_token,
    first_account_needing_setup,
    list_accounts_needing_setup,
    list_accounts_public,
    list_login_options,
    logout_response,
    needs_setup,
    request_payload,
    resolve_request_branch,
    set_password_first_time,
    verify_login_account,
    ws_role_allowed,
)

auth_configure(DATA_DIR)

from branch_data import (
    append_branch,
    configure as branch_configure,
    load_branch_today,
    load_branches,
    load_display_content,
    resolve_effective_branch,
    save_branch_today,
    save_display_content,
    tel_branch_key,
)

branch_configure(DATA_DIR)


def _request_branch(request: Request, branch: Optional[str] = None) -> str:
    bid = resolve_request_branch(branch, request.headers.get("host"))
    if not bid:
        raise HTTPException(status_code=400, detail="지점을 확인할 수 없습니다.")
    return bid


def _scoped_payload_or_401(request: Request, branch: Optional[str] = None) -> dict[str, Any]:
    payload = request_payload(request)
    if not payload:
        raise HTTPException(status_code=401, detail="인증되지 않았습니다.")
    if not branch_allows_request(payload, branch, request.headers.get("host")):
        raise HTTPException(status_code=403, detail="다른 지점에는 접근할 수 없습니다.")
    return payload

from db_config import (
    ensure_database_url_or_exit,
    init_db,
    running_on_railway,
    validate_mysql_database_url_or_exit,
)
from db_repo import migrate_from_data_dir
from kst_time import today_str_kst

ensure_database_url_or_exit()

try:
    validate_mysql_database_url_or_exit()
    init_db()
    migrate_from_data_dir(DATA_DIR)
except SystemExit:
    raise
except OperationalError:
    print(
        "MySQL 연결 실패 (OperationalError). Deploy Logs 위쪽에 상세 원인이 있습니다.\n"
        "· Variables: DATABASE_URL 또는 MYSQL_URL 이 이 프로젝트의 MySQL을 가리키는지\n"
        "· (2003) 타임아웃이면 호스트/포트·방화벽·SSL 요구 여부를 확인하세요.",
        file=sys.stderr,
    )
    traceback.print_exc()
    raise
except Exception:
    print(
        "--- DB 초기화 실패 (Railway Deploy Logs 에서 아래 Traceback 확인) ---",
        file=sys.stderr,
    )
    traceback.print_exc()
    raise

DEFAULT_MEAL_DURATION_MINUTES = 120
YCHOWON_MEAL_DURATION_MINUTES = 105

from room_config import CONFIG_FILENAME, ensure_example_file, load_room_options

ensure_example_file(DATA_DIR)
ROOM_OPTIONS = load_room_options(DATA_DIR)


def _today_str() -> str:
    return today_str_kst()


ROOM_TEXT_SEPARATOR = ", "


def _normalize_room_label(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _normalize_rooms(raw_rooms: Any, raw_room: Any = None) -> list[str]:
    values: list[Any] = []
    if isinstance(raw_rooms, (list, tuple, set)):
        values.extend(list(raw_rooms))
    elif raw_rooms is not None and str(raw_rooms).strip():
        values.append(raw_rooms)
    elif raw_room is not None and str(raw_room).strip():
        values.append(raw_room)

    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        parts = raw if isinstance(raw, (list, tuple, set)) else str(raw).split(",")
        for part in parts:
            label = _normalize_room_label(part)
            if not label or label in seen:
                continue
            seen.add(label)
            out.append(label)
    return out


def _format_room_text(rooms: list[str]) -> str:
    return ROOM_TEXT_SEPARATOR.join(rooms)


def _reservation_rooms(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    return _normalize_rooms(item.get("rooms"), item.get("room"))


def _reservation_room_text(item: Any) -> str:
    return _format_room_text(_reservation_rooms(item))


def _primary_room_text(item: Any) -> str:
    rooms = _reservation_rooms(item) if isinstance(item, dict) else _normalize_rooms(item)
    return rooms[0] if rooms else ""


def _rooms_overlap(rooms_a: list[str], rooms_b: list[str]) -> bool:
    if not rooms_a or not rooms_b:
        return False
    return not set(rooms_a).isdisjoint(rooms_b)


def _reservation_matches_ref(item: dict[str, Any], source: str, reservation_id: str) -> bool:
    return str(item.get("source") or "") == source and str(item.get("id") or "") == reservation_id


def _reservation_date_text(item: dict[str, Any], fallback: str = "") -> str:
    return str(item.get("date") or fallback or "")


def _assert_no_room_overlap_with_others(
    rooms: list[str],
    time_text: str,
    others: list[dict[str, Any]],
    detail: str,
    branch_id: Optional[str] = None,
) -> None:
    for other in others:
        if _rooms_overlap(rooms, _reservation_rooms(other)) and _times_overlap(
            str(other.get("time") or ""),
            time_text,
            branch_id,
        ):
            raise HTTPException(status_code=409, detail=detail)


def _get_admin_today_list(branch_id: str) -> list:
    """직원(admin)이 저장한 당일 목록만 (지점별 MySQL)."""
    data = load_branch_today(branch_id)
    if data.get("date") != _today_str():
        return []
    items = data.get("reservations") or []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rooms = _reservation_rooms(item)
        normalized.append({**item, "rooms": rooms, "room": _format_room_text(rooms)})
    return sorted(normalized, key=lambda x: (x.get("time", ""), _primary_room_text(x)))


def _get_board_today_merged(branch_id: str) -> list:
    """현황판·admin 목록용: 당일 직원 입력 + 당일 전화 예약(tel) 합침 (지점별)."""
    merged = []
    for r in _get_admin_today_list(branch_id):
        rooms = _reservation_rooms(r)
        merged.append({
            "id": r.get("id"),
            "time": r.get("time", ""),
            "name": r.get("name", ""),
            "room": _format_room_text(rooms),
            "rooms": rooms,
            "source": "admin",
            "count": r.get("count"),
            "adult": r.get("adult"),
            "child": r.get("child"),
            "infant": r.get("infant"),
        })
    for r in _get_tel_reservations(_today_str(), branch_id):
        tid = r.get("id")
        rooms = _reservation_rooms(r)
        merged.append({
            "id": f"tel-{tid}",
            "time": r.get("time", ""),
            "name": r.get("name", ""),
            "room": _format_room_text(rooms),
            "rooms": rooms,
            "source": "tel",
            "phone": r.get("phone", ""),
            "count": r.get("count"),
            "adult": r.get("adult"),
            "child": r.get("child"),
            "infant": r.get("infant"),
        })
    merged.sort(key=lambda x: (x.get("time", ""), str(x.get("id", ""))))
    return merged


def _rollover_branch_today_if_stale(branch_id: str) -> bool:
    """today 파일의 date가 오늘이 아니면 직원 당일 예약을 비우고 오늘 날짜로 맞춤 (자정 이후 첫 접근 시)."""
    data = load_branch_today(branch_id)
    if (data.get("date") or "") == _today_str():
        return False
    save_branch_today(branch_id, {"date": _today_str(), "reservations": []})
    return True


def _is_ychowon_branch(branch_id: Optional[str]) -> bool:
    return str(branch_id or "").strip().lower() == "ychowon"


def _meal_duration_minutes(branch_id: Optional[str] = None) -> int:
    return YCHOWON_MEAL_DURATION_MINUTES if _is_ychowon_branch(branch_id) else DEFAULT_MEAL_DURATION_MINUTES


def _room_overlap_detail(branch_id: Optional[str] = None) -> str:
    if _is_ychowon_branch(branch_id):
        return "기본 사용시간 1시간 45분 기준으로 이미 예약된 호실/테이블입니다."
    return "기본 식사시간 2시간 기준으로 이미 예약된 호실/테이블입니다."


def _time_slot(time_text: str, branch_id: Optional[str] = None) -> str:
    start_minutes = _parse_time_minutes(time_text)
    if start_minutes is None:
        return "other"
    if _is_ychowon_branch(branch_id):
        if 11 * 60 + 30 <= start_minutes <= 15 * 60 + 30:
            return "lunch"
        if 16 * 60 <= start_minutes <= 19 * 60 + 30:
            return "dinner"
        return "other"
    if 12 * 60 <= start_minutes <= 14 * 60 + 59:
        return "lunch"
    if 17 * 60 <= start_minutes <= 19 * 60 + 59:
        return "dinner"
    return "other"


def _parse_time_minutes(time_text: str) -> Optional[int]:
    try:
        hour_text, minute_text = (time_text or "").split(":")
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour * 60 + minute
    except (AttributeError, TypeError, ValueError):
        return None


def _format_time_minutes(total_minutes: int) -> str:
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _reservation_end_time(time_text: str, branch_id: Optional[str] = None) -> str:
    start_minutes = _parse_time_minutes(time_text)
    if start_minutes is None:
        return time_text
    return _format_time_minutes(start_minutes + _meal_duration_minutes(branch_id))


def _reservation_range_text(time_text: str, branch_id: Optional[str] = None) -> str:
    if not time_text:
        return ""
    return f"{time_text}~{_reservation_end_time(time_text, branch_id)}"


def _covers_time(start_time: str, target_time: str, branch_id: Optional[str] = None) -> bool:
    start_minutes = _parse_time_minutes(start_time)
    target_minutes = _parse_time_minutes(target_time)
    if start_minutes is None or target_minutes is None:
        return start_time == target_time
    end_minutes = start_minutes + _meal_duration_minutes(branch_id)
    return start_minutes <= target_minutes <= end_minutes


def _times_overlap(time_a: str, time_b: str, branch_id: Optional[str] = None) -> bool:
    start_a = _parse_time_minutes(time_a)
    start_b = _parse_time_minutes(time_b)
    if start_a is None or start_b is None:
        return time_a == time_b
    duration = _meal_duration_minutes(branch_id)
    end_a = start_a + duration
    end_b = start_b + duration
    return start_a <= end_b and start_b <= end_a


def _load_tel() -> dict:
    from db_repo import load_tel_store

    return load_tel_store()


def _save_tel(data: dict) -> None:
    from db_repo import save_tel_store

    save_tel_store(data)


def _active_display_slides(branch_id: str, data: Optional[dict[str, Any]] = None) -> list:
    if data is None:
        data = load_display_content(branch_id)
    try:
        default_dur = int(data.get("default_interval_sec") or 8)
    except (TypeError, ValueError):
        default_dur = 8
    default_dur = max(3, min(600, default_dur))
    items = list(data.get("items") or [])
    items.sort(key=lambda x: (int(x.get("order") or 0), str(x.get("id", ""))))
    out = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        t = (it.get("type") or "image").lower()
        if t not in ("video", "image"):
            t = "image"
        if t == "video":
            out.append({"type": "video", "url": url})
            continue
        try:
            dur_raw = it.get("duration_sec")
            dur_i = max(3, min(600, int(dur_raw))) if dur_raw is not None and str(dur_raw).strip() != "" else default_dur
        except (TypeError, ValueError):
            dur_i = default_dur
        out.append({"type": "image", "url": url, "duration_sec": dur_i})
    return out


def _active_top_display_slides(branch_id: str, data: Optional[dict[str, Any]] = None) -> list:
    if data is None:
        data = load_display_content(branch_id)
    try:
        default_dur = int(data.get("top_default_interval_sec") or 8)
    except (TypeError, ValueError):
        default_dur = 8
    default_dur = max(3, min(600, default_dur))
    items = list(data.get("top_items") or [])
    items.sort(key=lambda x: (int(x.get("order") or 0), str(x.get("id", ""))))
    out = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        t = (it.get("type") or "image").lower()
        if t not in ("video", "image"):
            t = "image"
        if t == "video":
            out.append({"type": "video", "url": url})
            continue
        try:
            dur_raw = it.get("duration_sec")
            dur_i = max(3, min(600, int(dur_raw))) if dur_raw is not None and str(dur_raw).strip() != "" else default_dur
        except (TypeError, ValueError):
            dur_i = default_dur
        out.append({"type": "image", "url": url, "duration_sec": dur_i})
    return out


def _display_content_push_payload(branch_id: str) -> dict[str, Any]:
    """WS·푸시용: active_slides + items(클라이언트 폴백) + default_interval_sec."""
    data = load_display_content(branch_id)
    try:
        di = int(data.get("default_interval_sec") or 8)
    except (TypeError, ValueError):
        di = 8
    di = max(3, min(600, di))
    try:
        top_di = int(data.get("top_default_interval_sec") or 8)
    except (TypeError, ValueError):
        top_di = 8
    top_di = max(3, min(600, top_di))
    return {
        "type": "display_content",
        "active_slides": _active_display_slides(branch_id, data),
        "active_top_slides": _active_top_display_slides(branch_id, data),
        "items": list(data.get("items") or []),
        "top_items": list(data.get("top_items") or []),
        "default_interval_sec": di,
        "top_default_interval_sec": top_di,
    }


def _display_version_push_payload() -> dict[str, str]:
    return {"type": "display_version", "version": DISPLAY_BUILD_VERSION}


def _get_tel_reservations(date_text: Optional[str] = None, branch_id: Optional[str] = None) -> list:
    data = _load_tel()
    items = data.get("reservations") or []
    normalized = []
    for item in items:
        slot = item.get("slot") or _time_slot(item.get("time", ""), tel_branch_key(item))
        rooms = _reservation_rooms(item)
        normalized.append({**item, "slot": slot, "source": "tel", "rooms": rooms, "room": _format_room_text(rooms)})
    if branch_id is not None:
        normalized = [item for item in normalized if tel_branch_key(item) == branch_id]
    if date_text:
        normalized = [item for item in normalized if item.get("date") == date_text]
    return sorted(normalized, key=lambda x: (x.get("date", ""), x.get("time", ""), _primary_room_text(x)))


def _staff_today_items_for_date(date_text: str, branch_id: str) -> list[dict]:
    """당일 직원 입력 예약을 전화 예약과 동일한 점유 판정에 쓸 형태로 반환."""
    data = load_branch_today(branch_id)
    if (data.get("date") or "") != date_text:
        return []
    out: list[dict] = []
    for r in data.get("reservations") or []:
        if not isinstance(r, dict):
            continue
        rooms = _reservation_rooms(r)
        if not rooms:
            continue
        t = str(r.get("time") or "")
        out.append(
            {
                "id": r.get("id"),
                "time": t,
                "room": _format_room_text(rooms),
                "rooms": rooms,
                "name": str(r.get("name") or ""),
                "slot": _time_slot(t, branch_id),
                "source": "staff",
            }
        )
    return out


def _room_status(
    date_text: str,
    time_text: str,
    branch_id: str,
    *,
    exclude_source: Optional[str] = None,
    exclude_id: Optional[str] = None,
) -> list:
    reservations = list(_get_tel_reservations(date_text, branch_id))
    reservations.extend(_staff_today_items_for_date(date_text, branch_id))
    by_room = {}
    for item in reservations:
        if exclude_source and exclude_id:
            if str(item.get("source") or "") == exclude_source and str(item.get("id") or "") == exclude_id:
                continue
        room_names = _reservation_rooms(item)
        if not room_names:
            continue
        for room_name in room_names:
            by_room.setdefault(room_name, []).append(item)

    result = []
    for room in ROOM_OPTIONS:
        room_items = by_room.get(room["label"], [])
        current = next(
            (item for item in room_items if _covers_time(item.get("time", ""), time_text, branch_id)),
            None,
        )
        occupied_ranges = []
        seen_ranges = set()
        for item in room_items:
            range_text = _reservation_range_text(item.get("time", ""), branch_id)
            if range_text and range_text not in seen_ranges:
                seen_ranges.add(range_text)
                occupied_ranges.append(range_text)
        result.append({
            **room,
            "reserved": bool(current),
            "reservation_name": (current or {}).get("name", ""),
            "time": (current or {}).get("time", ""),
            "reservation_range": _reservation_range_text((current or {}).get("time", ""), branch_id),
            "occupied_ranges": occupied_ranges,
        })
    return result


async def broadcast_reservations(branch_id: str) -> None:
    payload = json.dumps(_get_board_today_merged(branch_id), ensure_ascii=False)
    dead = set()
    for ws in list(ws_by_branch.get(branch_id, ())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        ws_by_branch[branch_id].discard(ws)


async def broadcast_display_content(branch_id: str) -> None:
    """현황판 하단 슬라이드 설정이 바뀌었을 때 해당 지점 WS 클라이언트에 푸시."""
    payload = json.dumps(_display_content_push_payload(branch_id), ensure_ascii=False)
    dead = set()
    for ws in list(ws_by_branch.get(branch_id, ())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        ws_by_branch[branch_id].discard(ws)


@app.websocket("/ws")
async def websocket_display(websocket: WebSocket, branch: str = Query(default="default")):
    try:
        bid = resolve_effective_branch(branch, websocket.headers.get("host"))
    except HTTPException:
        await websocket.close(code=4400)
        return
    if not ws_role_allowed(websocket, bid):
        await websocket.close(code=4401)
        return
    if _rollover_branch_today_if_stale(bid):
        await broadcast_reservations(bid)
    await websocket.accept()
    ws_by_branch[bid].add(websocket)
    try:
        await websocket.send_text(json.dumps(_display_version_push_payload(), ensure_ascii=False))
        await websocket.send_text(json.dumps(_get_board_today_merged(bid), ensure_ascii=False))
        await websocket.send_text(json.dumps(_display_content_push_payload(bid), ensure_ascii=False))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_by_branch[bid].discard(websocket)


class ReservationItem(BaseModel):
    id: Optional[int] = None
    time: str
    name: str
    room: str = ""
    rooms: Optional[list[str]] = None
    count: int = 2
    adult: Optional[int] = None
    child: Optional[int] = None
    infant: Optional[int] = None


class TodayReservations(BaseModel):
    reservations: list[ReservationItem]


class ReservationRoomSwapIn(BaseModel):
    first_source: str
    first_id: str
    second_source: str
    second_id: str


class TelReservationItem(BaseModel):
    id: Optional[int] = None
    date: str
    time: str
    phone: str
    name: str
    note: Optional[str] = None
    room: str = ""
    rooms: Optional[list[str]] = None
    count: int = 2
    adult: Optional[int] = None
    child: Optional[int] = None
    infant: Optional[int] = None
    slot: Optional[str] = None


class BranchCreateIn(BaseModel):
    id: str
    name: str = ""


@app.get("/api/branches")
def api_get_branches(request: Request, branch: str = Query(default="default")):
    """등록된 지점 목록 (현황·예약·광고 구분용)."""
    payload = _scoped_payload_or_401(request, branch)
    acc_branch = account_branch_from_payload(payload)
    if acc_branch:
        rows = [b for b in load_branches() if str(b.get("id") or "").strip().lower() == acc_branch]
        return {"branches": rows}
    return {"branches": load_branches()}


@app.post("/api/branches")
def api_post_branches(body: BranchCreateIn, request: Request):
    """관리자: 지점 추가 (당일·하단 광고 파일이 함께 생성됨)."""
    payload = _scoped_payload_or_401(request, None)
    if account_branch_from_payload(payload):
        raise HTTPException(status_code=403, detail="지점 전용 관리자 계정은 지점을 추가할 수 없습니다.")
    try:
        append_branch(body.id.strip(), (body.name or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "branches": load_branches()}


@app.get("/api/reservations/today")
async def get_today_reservations(
    request: Request,
    background_tasks: BackgroundTasks,
    branch: str = Query(default="default"),
):
    """당일 현황판용: 직원 입력 + 전화 예약(tel) 합친 목록 (지점별). 날짜가 바뀌었으면 직원 당일 파일을 초기화."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    if _rollover_branch_today_if_stale(bid):
        background_tasks.add_task(broadcast_reservations, bid)
    return _get_board_today_merged(bid)


@app.post("/api/reservations/today")
async def set_today_reservations(
    request: Request,
    payload: TodayReservations,
    branch: str = Query(default="default"),
):
    """직원(admin) 당일 예약만 통째로 교체. 전화 예약(tel)은 그대로 두고 합쳐서 현황판에 반영."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    items = []
    for r in payload.reservations:
        item = r.model_dump()
        rooms = _normalize_rooms(item.get("rooms"), item.get("room"))
        item["rooms"] = rooms
        item["room"] = _format_room_text(rooms)
        items.append(item)
    for i, r in enumerate(items):
        if r.get("id") is None:
            r["id"] = i + 1
    date_str = _today_str()
    tel_day = _get_tel_reservations(date_str, bid)
    for i, a in enumerate(items):
        ra = _reservation_rooms(a)
        ta = str(a.get("time") or "")
        if not ra or not ta:
            continue
        for t in tel_day:
            if _rooms_overlap(_reservation_rooms(t), ra) and _times_overlap(str(t.get("time") or ""), ta, bid):
                raise HTTPException(
                    status_code=409,
                    detail="전화 예약과 시간이 겹칩니다. 해당 호실/시간은 전화 예약 화면에서 확인하세요.",
                )
        for b in items[i + 1 :]:
            rb = _reservation_rooms(b)
            tb = str(b.get("time") or "")
            if _rooms_overlap(ra, rb) and tb and _times_overlap(ta, tb, bid):
                raise HTTPException(
                    status_code=409,
                    detail="같은 호실에서 식사 시간(2시간)이 겹치는 예약은 넣을 수 없습니다.",
                )
    data = {"date": date_str, "reservations": items}
    save_branch_today(bid, data)
    await broadcast_reservations(bid)
    return {"ok": True, "count": len(items)}


@app.delete("/api/reservations/today/{reservation_id}")
async def delete_today_reservation(
    request: Request,
    reservation_id: int,
    branch: str = Query(default="default"),
):
    """??(admin) ?? ?? ? ? ??."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    today = _today_str()
    data = load_branch_today(bid)
    items = list(data.get("reservations") or []) if data.get("date") == today else []

    removed = None
    kept = []
    for item in items:
        if int(item.get("id", 0) or 0) == reservation_id:
            removed = item
            continue
        kept.append(item)

    if removed is None:
        raise HTTPException(status_code=404, detail="??? ?? ??? ?? ? ????.")

    save_branch_today(bid, {"date": today, "reservations": kept})
    await broadcast_reservations(bid)
    return {"ok": True}


@app.post("/api/reservations/today/swap-rooms")
async def swap_today_reservation_rooms(
    request: Request,
    payload: ReservationRoomSwapIn,
    branch: str = Query(default="default"),
):
    """두 예약의 룸/테이블을 원자적으로 서로 교환."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    today = _today_str()
    first_source = str(payload.first_source or "").strip().lower()
    second_source = str(payload.second_source or "").strip().lower()
    first_id = str(payload.first_id or "").strip()
    second_id = str(payload.second_id or "").strip()

    if first_source not in ("staff", "tel") or second_source not in ("staff", "tel"):
        raise HTTPException(status_code=400, detail="교환할 예약 종류가 올바르지 않습니다.")
    if not first_id or not second_id:
        raise HTTPException(status_code=400, detail="교환할 예약을 확인할 수 없습니다.")
    if first_source == second_source and first_id == second_id:
        raise HTTPException(status_code=400, detail="같은 예약끼리는 교환할 수 없습니다.")

    admin_data = load_branch_today(bid)
    admin_items = list(admin_data.get("reservations") or []) if admin_data.get("date") == today else []
    tel_store = _load_tel()
    tel_items = list(tel_store.get("reservations") or [])
    tel_index_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for idx, item in enumerate(tel_items):
        if not isinstance(item, dict):
            continue
        if tel_branch_key(item) != bid:
            continue
        tel_index_by_id[str(item.get("id") or "")] = (idx, item)

    first_item = None
    second_item = None
    first_admin_index = None
    second_admin_index = None
    first_tel_index = None
    second_tel_index = None

    if first_source == "staff" or second_source == "staff":
        for idx, item in enumerate(admin_items):
            if not isinstance(item, dict):
                continue
            ref_id = str(item.get("id") or "")
            if first_source == "staff" and ref_id == first_id:
                first_item = item
                first_admin_index = idx
            if second_source == "staff" and ref_id == second_id:
                second_item = item
                second_admin_index = idx

    if first_source == "tel" or second_source == "tel":
        if first_source == "tel":
            matched = tel_index_by_id.get(first_id)
            if matched:
                first_tel_index, first_item = matched
        if second_source == "tel":
            matched = tel_index_by_id.get(second_id)
            if matched:
                second_tel_index, second_item = matched

    if first_item is None or second_item is None:
        raise HTTPException(status_code=404, detail="교환할 예약을 찾을 수 없습니다.")

    first_date = _reservation_date_text(first_item, today if first_source == "staff" else "")
    second_date = _reservation_date_text(second_item, today if second_source == "staff" else "")
    if not first_date or not second_date:
        raise HTTPException(status_code=400, detail="교환할 예약의 날짜를 확인할 수 없습니다.")
    if first_date != second_date:
        raise HTTPException(status_code=400, detail="같은 날짜 예약끼리만 교환할 수 있습니다.")
    if (first_source == "staff" or second_source == "staff") and first_date != today:
        raise HTTPException(status_code=400, detail="직원 당일 예약은 오늘 날짜에서만 교환할 수 있습니다.")

    first_rooms = _reservation_rooms(first_item)
    second_rooms = _reservation_rooms(second_item)
    if not first_rooms or not second_rooms:
        raise HTTPException(status_code=400, detail="교환할 호실/테이블 정보가 없습니다.")

    excluded = {
        (first_source, first_id),
        (second_source, second_id),
    }
    others: list[dict[str, Any]] = []
    for item in _staff_today_items_for_date(first_date, bid):
        if _reservation_matches_ref(item, "staff", str(item.get("id") or "")) and ("staff", str(item.get("id") or "")) in excluded:
            continue
        if ("staff", str(item.get("id") or "")) not in excluded:
            others.append(item)
    for item in _get_tel_reservations(first_date, bid):
        if ("tel", str(item.get("id") or "")) not in excluded:
            others.append(item)

    _assert_no_room_overlap_with_others(
        second_rooms,
        str(first_item.get("time") or ""),
        others,
        "교환 후 첫 번째 예약의 호실/테이블이 다른 예약과 겹칩니다.",
        bid,
    )
    _assert_no_room_overlap_with_others(
        first_rooms,
        str(second_item.get("time") or ""),
        others,
        "교환 후 두 번째 예약의 호실/테이블이 다른 예약과 겹칩니다.",
        bid,
    )

    first_item["rooms"] = list(second_rooms)
    first_item["room"] = _format_room_text(second_rooms)
    second_item["rooms"] = list(first_rooms)
    second_item["room"] = _format_room_text(first_rooms)

    if first_admin_index is not None or second_admin_index is not None:
        save_branch_today(bid, {"date": today, "reservations": admin_items})
    if first_tel_index is not None or second_tel_index is not None:
        _save_tel({"reservations": tel_items})

    await broadcast_reservations(bid)
    return {"ok": True}


@app.get("/api/tel/reservations")
def get_tel_reservations(
    request: Request,
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch: str = Query(default="default"),
):
    """전화 예약 목록. date 단일 지정 시 해당 일만. 그 외 date_from·date_to로 기간 필터(둘 다 생략 시 전체)."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    if date:
        return _get_tel_reservations(date, bid)
    items = _get_tel_reservations(None, bid)
    if date_from:
        items = [i for i in items if (i.get("date") or "") >= date_from]
    if date_to:
        items = [i for i in items if (i.get("date") or "") <= date_to]
    return sorted(
        items,
        key=lambda x: (x.get("date", ""), x.get("time", ""), _primary_room_text(x)),
    )


@app.get("/api/tel/rooms")
def get_tel_room_status(
    request: Request,
    date: str,
    time: str,
    exclude_id: Optional[str] = None,
    exclude_source: Optional[str] = None,
    branch: str = Query(default="default"),
):
    """날짜+시간 기준 호실/테이블 예약 가능 상태."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    return {
        "date": date,
        "time": time,
        "slot": _time_slot(time, bid),
        "rooms": _room_status(date, time, bid, exclude_id=exclude_id, exclude_source=exclude_source),
    }


@app.post("/api/tel/reservations")
async def create_tel_reservation(
    request: Request,
    payload: TelReservationItem,
    branch: str = Query(default="default"),
):
    """전화 예약 접수 등록. 당일이면 현황판에 즉시 반영."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    items = _get_tel_reservations()
    slot = payload.slot or _time_slot(payload.time, bid)
    rooms = _normalize_rooms(payload.rooms, payload.room)
    if not rooms:
        raise HTTPException(status_code=400, detail="호실/테이블을 하나 이상 선택하세요.")

    for item in items:
        if tel_branch_key(item) != bid:
            continue
        if (
            item.get("date") == payload.date
            and _rooms_overlap(_reservation_rooms(item), rooms)
            and _times_overlap(item.get("time", ""), payload.time, bid)
        ):
            raise HTTPException(status_code=409, detail=_room_overlap_detail(bid))

    for s in _staff_today_items_for_date(payload.date, bid):
        if _rooms_overlap(_reservation_rooms(s), rooms) and _times_overlap(s.get("time", ""), payload.time, bid):
            raise HTTPException(
                status_code=409,
                detail="직원 당일 예약과 시간이 겹칩니다. 관리자 화면에서 해당 호실/시간을 확인하세요.",
            )

    next_id = max([int(item.get("id", 0) or 0) for item in items] + [0]) + 1
    new_item = {
        "id": next_id,
        "branch_id": bid,
        "date": payload.date,
        "time": payload.time,
        "slot": slot,
        "phone": payload.phone,
        "name": payload.name,
        "note": str(payload.note or "").strip(),
        "count": payload.count,
        "room": _format_room_text(rooms),
        "rooms": rooms,
        "adult": payload.adult,
        "child": payload.child,
        "infant": payload.infant,
    }
    items.append(new_item)
    _save_tel({"reservations": items})
    if payload.date == _today_str():
        await broadcast_reservations(bid)
    return {"ok": True, "item": new_item}


class TelReservationPatch(BaseModel):
    time: Optional[str] = None
    name: Optional[str] = None
    room: Optional[str] = None
    rooms: Optional[list[str]] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    count: Optional[int] = None
    adult: Optional[int] = None
    child: Optional[int] = None
    infant: Optional[int] = None


class DisplayContentItemIn(BaseModel):
    id: str = ""
    type: str = "image"
    url: str = ""
    name: Optional[str] = None
    duration_sec: Optional[int] = None
    order: int = 0


class DisplayContentIn(BaseModel):
    items: list[DisplayContentItemIn] = []
    default_interval_sec: int = 8
    top_items: list[DisplayContentItemIn] = []
    top_default_interval_sec: int = 8


@app.get("/api/display/content")
def api_get_display_content(request: Request, branch: str = Query(default="default")):
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    data = load_display_content(bid)
    try:
        di = int(data.get("default_interval_sec") or 8)
    except (TypeError, ValueError):
        di = 8
    try:
        top_di = int(data.get("top_default_interval_sec") or 8)
    except (TypeError, ValueError):
        top_di = 8
    raw_items = data.get("items") or []
    raw_top_items = data.get("top_items") or []
    items_out = []
    for it in raw_items:
        row = dict(it)
        url = str(row.get("url") or "")
        filled = _fill_display_name_from_upload_meta(url, str(row.get("name") or ""))
        if filled:
            row["name"] = filled
        items_out.append(row)
    top_items_out = []
    for it in raw_top_items:
        row = dict(it)
        url = str(row.get("url") or "")
        filled = _fill_display_name_from_upload_meta(url, str(row.get("name") or ""))
        if filled:
            row["name"] = filled
        top_items_out.append(row)
    return JSONResponse(
        content={
            "items": items_out,
            "top_items": top_items_out,
            "default_interval_sec": max(3, min(600, di)),
            "top_default_interval_sec": max(3, min(600, top_di)),
            "active_slides": _active_display_slides(bid),
            "active_top_slides": _active_top_display_slides(bid),
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/display/content")
async def api_set_display_content(
    request: Request,
    payload: DisplayContentIn,
    branch: str = Query(default="default"),
):
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    old_data = load_display_content(bid)

    def _normalize_display_items(raw_items: list[DisplayContentItemIn]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for it in raw_items:
            d = it.model_dump()
            url = (d.get("url") or "").strip()
            if not url:
                continue
            if not url.startswith(("http://", "https://", "/")):
                raise HTTPException(
                    status_code=400,
                    detail="URL은 http(s) 또는 / 로 시작하는 경로만 가능합니다.",
                )
            t = (d.get("type") or "image").lower()
            is_video = t == "video"
            entry: dict[str, Any] = {
                "type": "video" if is_video else "image",
                "url": url,
            }
            nm = str(d.get("name") or "").strip()[:200]
            nm = _fill_display_name_from_upload_meta(url, nm)
            if nm:
                entry["name"] = nm
            if not is_video and d.get("duration_sec") is not None:
                entry["duration_sec"] = d.get("duration_sec")
            normalized.append(entry)
        for idx, row in enumerate(normalized):
            row["id"] = str(idx + 1)
            row["order"] = idx
        return normalized

    normalized = _normalize_display_items(payload.items)
    top_normalized = _normalize_display_items(payload.top_items)
    try:
        di = int(payload.default_interval_sec)
        di = max(3, min(600, di))
    except (TypeError, ValueError):
        di = 8
    try:
        top_di = int(payload.top_default_interval_sec)
        top_di = max(3, min(600, top_di))
    except (TypeError, ValueError):
        top_di = 8
    new_urls = {str(d.get("url") or "").strip() for d in (normalized + top_normalized)}
    old_items = list(old_data.get("items") or []) + list(old_data.get("top_items") or [])
    _cleanup_removed_display_uploads(old_items, new_urls)
    save_display_content(
        bid,
        {
            "items": normalized,
            "default_interval_sec": di,
            "top_items": top_normalized,
            "top_default_interval_sec": top_di,
        },
    )
    await broadcast_display_content(bid)
    return {"ok": True, "active_slides": _active_display_slides(bid)}


_DISPLAY_UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".mov", ".m4v"}
_DISPLAY_UPLOAD_MAX = 50 * 1024 * 1024


def _display_uploads_dir() -> Path:
    return DISPLAY_DIR / "uploads"


def _original_name_from_uploaded_file(stored_filename: str) -> str:
    """업로드 시 저장한 .meta.json 에서 사용자가 고른 원본 파일명을 읽습니다."""
    if not stored_filename or ".." in stored_filename or "/" in stored_filename or "\\" in stored_filename:
        return ""
    meta = _display_uploads_dir() / f"{stored_filename}.meta.json"
    if not meta.is_file():
        return ""
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return str(data.get("original_name") or "").strip()[:200]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return ""


def _fill_display_name_from_upload_meta(url: str, current_name: str) -> str:
    nm = str(current_name or "").strip()
    if nm:
        return nm
    u = (url or "").strip()
    try:
        from r2_storage import head_original_name, is_r2_public_url

        if is_r2_public_url(u):
            got = head_original_name(u)
            return got if got else ""
    except Exception:
        pass
    if not u.startswith("/display/uploads/"):
        return ""
    part = u.split("/")[-1].split("?")[0]
    return _original_name_from_uploaded_file(part)


def _cleanup_removed_display_uploads(old_items: list, new_urls: set) -> None:
    """관리 화면에서 항목이 빠지면 로컬 display/uploads 또는 R2 객체를 삭제합니다."""
    try:
        from r2_storage import delete_object_by_public_url, is_r2_public_url
    except Exception:

        def is_r2_public_url(_u: str) -> bool:  # type: ignore[misc]
            return False

        def delete_object_by_public_url(_u: str) -> None:  # type: ignore[misc]
            return None

    base = _display_uploads_dir().resolve()
    norm_new = {str(x).strip().split("?")[0] for x in new_urls}
    for it in old_items:
        url = str(it.get("url") or "").strip()
        u = url.split("?")[0]
        if not u or u in norm_new:
            continue
        if is_r2_public_url(u):
            try:
                delete_object_by_public_url(u)
            except Exception:
                pass
            continue
        if not u.startswith("/display/uploads/"):
            continue
        part = u.split("/")[-1].split("?")[0]
        if not part or ".." in part or "/" in part or "\\" in part:
            continue
        try:
            media = (base / part).resolve()
        except OSError:
            continue
        if not str(media).startswith(str(base)):
            continue
        if media.is_file():
            try:
                media.unlink()
            except OSError:
                pass
        try:
            meta = (base / f"{part}.meta.json").resolve()
        except OSError:
            continue
        if str(meta).startswith(str(base)) and meta.is_file():
            try:
                meta.unlink()
            except OSError:
                pass


@app.post("/api/display/upload")
async def api_upload_display_asset(file: UploadFile = File(...)):
    """현황판 하단용 이미지·동영상은 Cloudflare R2에만 저장합니다 (로컬 폴백 없음)."""
    from r2_storage import r2_enabled, r2_upload_unavailable_message, upload_display_bytes

    if not r2_enabled():
        raise HTTPException(status_code=503, detail=r2_upload_unavailable_message())

    raw_name = (file.filename or "file").replace("\\", "/").split("/")[-1]
    suffix = Path(raw_name).suffix.lower()
    if suffix not in _DISPLAY_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail="허용 확장자: " + ", ".join(sorted(_DISPLAY_UPLOAD_EXTS)),
        )
    body = await file.read()
    if len(body) > _DISPLAY_UPLOAD_MAX:
        raise HTTPException(status_code=400, detail="파일 크기는 50MB 이하만 가능합니다.")

    try:
        public_url = upload_display_bytes(body, suffix, raw_name)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="R2 업로드 실패: " + str(e),
        ) from e
    return {"url": public_url, "original_name": raw_name}


@app.patch("/api/tel/reservations/{reservation_id}")
async def patch_tel_reservation(
    request: Request,
    reservation_id: int,
    payload: TelReservationPatch,
    branch: str = Query(default="default"),
):
    """전화 예약 수정 (admin·당일 현황 연동)."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    items = _get_tel_reservations()
    idx = next((i for i, x in enumerate(items) if int(x.get("id", 0) or 0) == reservation_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    cur = dict(items[idx])
    if tel_branch_key(cur) != bid:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    new_time = payload.time if payload.time is not None else cur.get("time", "")
    if payload.rooms is not None or payload.room is not None:
        new_rooms = _normalize_rooms(payload.rooms, payload.room)
    else:
        new_rooms = _reservation_rooms(cur)
    new_name = payload.name if payload.name is not None else cur.get("name", "")
    new_phone = payload.phone if payload.phone is not None else cur.get("phone", "")
    new_note = payload.note if payload.note is not None else cur.get("note", "")
    date = cur.get("date", "")
    if not new_rooms:
        raise HTTPException(status_code=400, detail="호실/테이블을 하나 이상 선택하세요.")
    for item in items:
        if int(item.get("id", 0) or 0) == reservation_id:
            continue
        if tel_branch_key(item) != bid:
            continue
        if item.get("date") == date and _rooms_overlap(_reservation_rooms(item), new_rooms) and _times_overlap(item.get("time", ""), new_time, bid):
            raise HTTPException(status_code=409, detail=_room_overlap_detail(bid))
    for s in _staff_today_items_for_date(date, bid):
        if _rooms_overlap(_reservation_rooms(s), new_rooms) and _times_overlap(s.get("time", ""), new_time, bid):
            raise HTTPException(
                status_code=409,
                detail="직원 당일 예약과 시간이 겹칩니다. 관리자 화면에서 해당 호실/시간을 확인하세요.",
            )
    cur["time"] = new_time
    cur["room"] = _format_room_text(new_rooms)
    cur["rooms"] = new_rooms
    cur["name"] = new_name
    cur["phone"] = new_phone
    cur["note"] = str(new_note or "").strip()
    if payload.count is not None:
        cur["count"] = int(payload.count)
    if payload.adult is not None:
        cur["adult"] = payload.adult
    if payload.child is not None:
        cur["child"] = payload.child
    if payload.infant is not None:
        cur["infant"] = payload.infant
    if any(
        x is not None
        for x in (payload.count, payload.adult, payload.child, payload.infant)
    ):
        a = cur.get("adult")
        c = cur.get("child")
        i = cur.get("infant")
        try:
            total = (int(a) if a is not None else 0) + (int(c) if c is not None else 0) + (int(i) if i is not None else 0)
        except (TypeError, ValueError):
            total = int(cur.get("count") or 0)
        if total > 0:
            cur["count"] = total
    cur["slot"] = _time_slot(new_time, bid)
    items[idx] = cur
    _save_tel({"reservations": items})
    if date == _today_str():
        await broadcast_reservations(bid)
    return {"ok": True, "item": cur}


@app.delete("/api/tel/reservations/{reservation_id}")
async def delete_tel_reservation(
    request: Request,
    reservation_id: int,
    branch: str = Query(default="default"),
):
    """전화 예약 삭제."""
    bid = resolve_effective_branch(branch, request.headers.get("host"))
    items = _get_tel_reservations()
    removed = None
    kept = []
    for x in items:
        if int(x.get("id", 0) or 0) == reservation_id:
            removed = x
            continue
        kept.append(x)
    if removed is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if tel_branch_key(removed) != bid:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    _save_tel({"reservations": kept})
    if removed.get("date") == _today_str():
        await broadcast_reservations(bid)
    return {"ok": True}


class AuthSetupBody(BaseModel):
    account_id: str
    password: str


class AuthLoginBody(BaseModel):
    account_id: str
    password: str


class AccountCreateIn(BaseModel):
    id: str
    name: str
    role: str
    password: str


class AccountPatchIn(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None


@app.get("/api/auth/status")
def api_auth_status(request: Request, role: str, branch: str = Query(default="default")):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="잘못된 역할입니다.")
    bid = _request_branch(request, branch)
    ns = needs_setup(role, bid)
    needing = list_accounts_needing_setup(role, bid) if ns else []
    fac = first_account_needing_setup(role, bid) if ns else None
    return {
        "needs_setup": ns,
        "role": role,
        "branch_id": bid,
        "default_account_id": fac,
        "accounts_needing_setup": needing,
    }


@app.get("/api/auth/login-options")
def api_auth_login_options(request: Request, role: str, branch: str = Query(default="default")):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="잘못된 역할입니다.")
    bid = _request_branch(request, branch)
    return {"accounts": list_login_options(role, bid), "branch_id": bid}


@app.get("/api/auth/session")
def api_auth_session(request: Request, branch: str = Query(default="default")):
    """유효한 access_token 쿠키가 있으면 역할·계정 정보 반환. 로그인 페이지에서 이미 로그인된 경우 바로 이동할 때 사용."""
    payload = request_payload(request)
    if not payload:
        raise HTTPException(status_code=401, detail="인증되지 않았습니다.")
    bid = _request_branch(request, branch)
    if not branch_allows_request(payload, bid, request.headers.get("host")):
        raise HTTPException(status_code=403, detail="다른 지점에는 접근할 수 없습니다.")
    role = payload.get("role")
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="인증되지 않았습니다.")
    return {
        "ok": True,
        "role": role,
        "account_id": payload.get("sub"),
        "name": payload.get("name"),
        "branch_id": account_branch_from_payload(payload),
    }


@app.post("/api/auth/setup")
def api_auth_setup(body: AuthSetupBody, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    try:
        u = set_password_first_time(body.account_id.strip(), body.password, bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_token(u["id"], u["role"], u["name"], u.get("branch_id"))
    r = JSONResponse({"ok": True, "account_id": u["id"], "role": u["role"], "branch_id": u.get("branch_id")})
    r.set_cookie(**auth_cookie_response(token, request))
    return r


@app.post("/api/auth/login")
def api_auth_login(body: AuthLoginBody, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    u = verify_login_account(body.account_id.strip(), body.password, bid)
    if not u:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    token = create_token(u["id"], u["role"], u["name"], u.get("branch_id"))
    r = JSONResponse({"ok": True, "account_id": u["id"], "role": u["role"], "branch_id": u.get("branch_id")})
    r.set_cookie(**auth_cookie_response(token, request))
    return r


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    return logout_response(request)


@app.get("/api/auth/accounts")
def api_auth_accounts_list(request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    _scoped_payload_or_401(request, bid)
    return {"accounts": list_accounts_public(bid), "branch_id": bid}


@app.post("/api/auth/accounts")
def api_auth_accounts_create(body: AccountCreateIn, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    _scoped_payload_or_401(request, bid)
    try:
        account_create(body.id.strip(), body.name, body.role, body.password, bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.patch("/api/auth/accounts/{account_id}")
def api_auth_accounts_patch(account_id: str, body: AccountPatchIn, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    _scoped_payload_or_401(request, bid)
    try:
        account_update(account_id.strip(), bid, name=body.name, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/api/auth/accounts/{account_id}")
def api_auth_accounts_delete(account_id: str, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    _scoped_payload_or_401(request, bid)
    try:
        account_delete(account_id.strip(), bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.post("/api/auth/accounts/{account_id}/revoke")
def api_auth_accounts_revoke(account_id: str, request: Request, branch: str = Query(default="default")):
    bid = _request_branch(request, branch)
    _scoped_payload_or_401(request, bid)
    try:
        account_revoke(account_id.strip(), bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.get("/api/branch-boot.js")
def branch_boot_js(request: Request):
    """API의 resolve_effective_branch 와 동일 규칙으로 기본 지점을 내려줌 (컨텐츠·현황과 정합)."""
    try:
        payload = request_payload(request)
        account_branch = account_branch_from_payload(payload) if payload else None
        bid = account_branch or resolve_effective_branch("default", request.headers.get("host"))
        env_literal = json.dumps(bid)
    except HTTPException:
        env_literal = "null"
    build_literal = json.dumps(DISPLAY_BUILD_VERSION)
    body = (
        f"window.__RESERVE_DEFAULT_BRANCH__={env_literal};\n"
        f"window.__RESERVE_BUILD_VERSION__={build_literal};\n"
        "(function(g){"
        "function inferHost(){try{var h=(g.location.hostname||'').toLowerCase();"
        "if(h.indexOf('ychowon')>=0)return'ychowon';"
        "if(h.indexOf('mchowon')>=0)return'mchowon';"
        "}catch(e){}return'';}"
        "g.reserveInferDefaultBranch=function(){"
        "var w=g.__RESERVE_DEFAULT_BRANCH__;"
        "if(w!=null&&String(w).trim())return String(w).trim().toLowerCase();"
        "var x=inferHost();if(x)return x;return'default';};"
        "g.reserveInstallBuildVersionWatcher=function(opts){"
        "opts=opts||{};"
        "var known=String(g.__RESERVE_BUILD_VERSION__||'').trim();"
        "if(!known)return;"
        "var interval=Math.max(5000,Number(opts.intervalMs)||15000);"
        "var path=opts.path||'/api/build-version';"
        "var stopped=false;"
        "function check(){"
        "if(stopped)return;"
        "fetch(path+'?_=' + Date.now(),{cache:'no-store',credentials:'same-origin'})"
        ".then(function(r){if(!r.ok)throw new Error('build-version');return r.json();})"
        ".then(function(data){"
        "var next=data&&data.version!=null?String(data.version).trim():'';"
        "if(next&&next!==known){g.location.reload();}"
        "})"
        ".catch(function(){});"
        "}"
        "check();"
        "var timer=g.setInterval(check,interval);"
        "return function(){stopped=true;try{g.clearInterval(timer);}catch(e){}};"
        "};"
        "})(window);\n"
    )
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/build-version")
def api_build_version():
    return JSONResponse(
        content={"version": DISPLAY_BUILD_VERSION},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


if DISPLAY_DIR.exists():
    app.mount("/display", StaticFiles(directory=str(DISPLAY_DIR), html=True), name="display")
if ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")
if TEL_DIR.exists():
    app.mount("/tel", StaticFiles(directory=str(TEL_DIR), html=True), name="tel")
if PRINT_DIR.exists():
    app.mount("/print", StaticFiles(directory=str(PRINT_DIR), html=True), name="print")
