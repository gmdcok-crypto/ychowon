"""
초원농원 예약 현황판 - 당일 전용, DB 없이 JSON 파일만 사용

로그·Invalid HTTP request 관련 (참고):
- favicon /sw.js 404 는 아래 고정 라우트로 완화.
- Invalid HTTP request 는 보통 HTTPS를 HTTP 포트로 보내거나 스캐너·봇이 섞인 요청이라
  앱으로는 차단 불가. 개발 시 --host 127.0.0.1 만 열기, 운영 시 방화벽·VPN·
  nginx/Caddy 리버스 프록시(TLS 종료) 뒤에 두면 노이즈가 줄어듦.
- 콘솔을 덜 시끄럽게: uvicorn --log-level warning (또는 error)
"""
import asyncio
import json
import socket
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Set

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

app = FastAPI(title="초원농원 예약 현황 API")

ws_connections: Set[WebSocket] = set()


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
    from room_config import ACTIVE_ROOMS_CONFIG_REF as _room_cfg_ref

    if _room_cfg_ref:
        print("  룸·홀:    data/%s (지점 설정)" % _room_cfg_ref)
    else:
        print("  룸·홀:    내장 기본값 (ROOMS_CONFIG_FILE 또는 data/%s)" % CONFIG_FILENAME)
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


@app.get("/display")
def display_redirect():
    """끝에 슬래시 없이 /display 로 접속해도 현황판으로."""
    return RedirectResponse(url="/display/")

# 현황판·관리자·태블릿 정적 경로 (app.mount 는 파일 맨 아래에서 등록 — /api 라우트가 먼저 매칭되도록)
DISPLAY_DIR = Path(__file__).resolve().parent.parent / "display"
ADMIN_DIR = Path(__file__).resolve().parent.parent / "admin"
TEL_DIR = Path(__file__).resolve().parent.parent / "tel"

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

# 당일 예약 저장 파일 (DB 대신 단일 JSON)
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

from auth_service import (
    ROLES,
    account_create,
    account_delete,
    account_revoke,
    account_update,
    auth_cookie_response,
    auth_middleware,
    configure as auth_configure,
    create_token,
    decode_token,
    extract_token,
    first_account_needing_setup,
    list_accounts_needing_setup,
    list_accounts_public,
    list_login_options,
    logout_response,
    needs_setup,
    set_password_first_time,
    verify_login_account,
    ws_role_allowed,
)

auth_configure(DATA_DIR)

TODAY_FILE = DATA_DIR / "today.json"
TEL_FILE = DATA_DIR / "tel_reservations.json"
DISPLAY_CONTENT_FILE = DATA_DIR / "display_content.json"
MEAL_DURATION_MINUTES = 120

from room_config import CONFIG_FILENAME, ensure_example_file, load_room_options

ensure_example_file(DATA_DIR)
ROOM_OPTIONS = load_room_options(DATA_DIR)


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load() -> dict:
    if not TODAY_FILE.exists():
        return {"date": _today_str(), "reservations": []}
    try:
        with open(TODAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"date": _today_str(), "reservations": []}


def _save(data: dict) -> None:
    with open(TODAY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_admin_today_list() -> list:
    """직원(admin)이 저장한 당일 목록만 (today.json)."""
    data = _load()
    if data.get("date") != _today_str():
        return []
    items = data.get("reservations") or []
    return sorted(items, key=lambda x: x.get("time", ""))


def _get_board_today_merged() -> list:
    """현황판·admin 목록용: 당일 직원 입력 + 당일 전화 예약(tel) 합침."""
    merged = []
    for r in _get_admin_today_list():
        merged.append({
            "id": r.get("id"),
            "time": r.get("time", ""),
            "name": r.get("name", ""),
            "room": r.get("room", ""),
            "source": "admin",
        })
    for r in _get_tel_reservations(_today_str()):
        tid = r.get("id")
        merged.append({
            "id": f"tel-{tid}",
            "time": r.get("time", ""),
            "name": r.get("name", ""),
            "room": r.get("room", ""),
            "source": "tel",
            "phone": r.get("phone", ""),
            "count": r.get("count"),
            "adult": r.get("adult"),
            "child": r.get("child"),
            "infant": r.get("infant"),
        })
    merged.sort(key=lambda x: (x.get("time", ""), str(x.get("id", ""))))
    return merged


def _time_slot(time_text: str) -> str:
    try:
        hour = int((time_text or "").split(":")[0])
    except (TypeError, ValueError, IndexError):
        return "other"
    if 12 <= hour <= 14:
        return "lunch"
    if 17 <= hour <= 19:
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


def _reservation_end_time(time_text: str) -> str:
    start_minutes = _parse_time_minutes(time_text)
    if start_minutes is None:
        return time_text
    return _format_time_minutes(start_minutes + MEAL_DURATION_MINUTES)


def _reservation_range_text(time_text: str) -> str:
    if not time_text:
        return ""
    return f"{time_text}~{_reservation_end_time(time_text)}"


def _covers_time(start_time: str, target_time: str) -> bool:
    start_minutes = _parse_time_minutes(start_time)
    target_minutes = _parse_time_minutes(target_time)
    if start_minutes is None or target_minutes is None:
        return start_time == target_time
    end_minutes = start_minutes + MEAL_DURATION_MINUTES
    return start_minutes <= target_minutes <= end_minutes


def _times_overlap(time_a: str, time_b: str) -> bool:
    start_a = _parse_time_minutes(time_a)
    start_b = _parse_time_minutes(time_b)
    if start_a is None or start_b is None:
        return time_a == time_b
    end_a = start_a + MEAL_DURATION_MINUTES
    end_b = start_b + MEAL_DURATION_MINUTES
    return start_a <= end_b and start_b <= end_a


def _load_tel() -> dict:
    if not TEL_FILE.exists():
        return {"reservations": []}
    try:
        with open(TEL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"reservations": []}


def _save_tel(data: dict) -> None:
    with open(TEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_display_content() -> dict:
    if not DISPLAY_CONTENT_FILE.exists():
        return {"items": [], "default_interval_sec": 8}
    try:
        with open(DISPLAY_CONTENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"items": [], "default_interval_sec": 8}


def _save_display_content(data: dict) -> None:
    with open(DISPLAY_CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _active_display_slides() -> list:
    data = _load_display_content()
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


def _get_tel_reservations(date_text: Optional[str] = None) -> list:
    data = _load_tel()
    items = data.get("reservations") or []
    normalized = []
    for item in items:
        slot = item.get("slot") or _time_slot(item.get("time", ""))
        normalized.append({**item, "slot": slot})
    if date_text:
        normalized = [item for item in normalized if item.get("date") == date_text]
    return sorted(normalized, key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("room", "")))


def _room_status(date_text: str, time_text: str) -> list:
    reservations = _get_tel_reservations(date_text)
    by_room = {}
    for item in reservations:
        room_name = item.get("room")
        if not room_name:
            continue
        by_room.setdefault(room_name, []).append(item)

    result = []
    for room in ROOM_OPTIONS:
        room_items = by_room.get(room["label"], [])
        current = next(
            (item for item in room_items if _covers_time(item.get("time", ""), time_text)),
            None,
        )
        occupied_ranges = []
        seen_ranges = set()
        for item in room_items:
            range_text = _reservation_range_text(item.get("time", ""))
            if range_text and range_text not in seen_ranges:
                seen_ranges.add(range_text)
                occupied_ranges.append(range_text)
        result.append({
            **room,
            "reserved": bool(current),
            "reservation_name": (current or {}).get("name", ""),
            "time": (current or {}).get("time", ""),
            "reservation_range": _reservation_range_text((current or {}).get("time", "")),
            "occupied_ranges": occupied_ranges,
        })
    return result


async def broadcast_reservations() -> None:
    payload = json.dumps(_get_board_today_merged(), ensure_ascii=False)
    dead = set()
    for ws in ws_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        ws_connections.discard(ws)


async def broadcast_display_content() -> None:
    """현황판 하단 슬라이드 설정이 바뀌었을 때 모든 WS 클라이언트에 푸시."""
    payload = json.dumps(
        {"type": "display_content", "active_slides": _active_display_slides()},
        ensure_ascii=False,
    )
    dead = set()
    for ws in ws_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        ws_connections.discard(ws)


@app.websocket("/ws")
async def websocket_display(websocket: WebSocket):
    if not ws_role_allowed(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ws_connections.add(websocket)
    try:
        await websocket.send_text(json.dumps(_get_board_today_merged(), ensure_ascii=False))
        await websocket.send_text(
            json.dumps(
                {"type": "display_content", "active_slides": _active_display_slides()},
                ensure_ascii=False,
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_connections.discard(websocket)


class ReservationItem(BaseModel):
    id: Optional[int] = None
    time: str
    name: str
    room: str


class TodayReservations(BaseModel):
    reservations: list[ReservationItem]


class TelReservationItem(BaseModel):
    id: Optional[int] = None
    date: str
    time: str
    phone: str
    name: str
    room: str
    count: int = 2
    adult: Optional[int] = None
    child: Optional[int] = None
    infant: Optional[int] = None
    slot: Optional[str] = None


@app.get("/api/reservations/today")
def get_today_reservations():
    """당일 현황판용: 직원 입력 + 전화 예약(tel) 합친 목록."""
    return _get_board_today_merged()


@app.post("/api/reservations/today")
async def set_today_reservations(payload: TodayReservations):
    """직원(admin) 당일 예약만 통째로 교체. 전화 예약(tel)은 그대로 두고 합쳐서 현황판에 반영."""
    items = [r.model_dump() for r in payload.reservations]
    for i, r in enumerate(items):
        if r.get("id") is None:
            r["id"] = i + 1
    data = {"date": _today_str(), "reservations": items}
    _save(data)
    await broadcast_reservations()
    return {"ok": True, "count": len(items)}


@app.get("/api/tel/reservations")
def get_tel_reservations(
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """전화 예약 목록. date 단일 지정 시 해당 일만. 그 외 date_from·date_to로 기간 필터(둘 다 생략 시 전체)."""
    if date:
        return _get_tel_reservations(date)
    items = _get_tel_reservations(None)
    if date_from:
        items = [i for i in items if (i.get("date") or "") >= date_from]
    if date_to:
        items = [i for i in items if (i.get("date") or "") <= date_to]
    return sorted(
        items,
        key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("room", "")),
    )


@app.get("/api/tel/rooms")
def get_tel_room_status(date: str, time: str):
    """날짜+시간 기준 호실/테이블 예약 가능 상태."""
    return {
        "date": date,
        "time": time,
        "slot": _time_slot(time),
        "rooms": _room_status(date, time),
    }


@app.post("/api/tel/reservations")
async def create_tel_reservation(payload: TelReservationItem):
    """전화 예약 접수 등록. 당일이면 현황판에 즉시 반영."""
    items = _get_tel_reservations()
    slot = payload.slot or _time_slot(payload.time)

    for item in items:
        if (
            item.get("date") == payload.date
            and item.get("room") == payload.room
            and _times_overlap(item.get("time", ""), payload.time)
        ):
            raise HTTPException(status_code=409, detail="기본 식사시간 2시간 기준으로 이미 예약된 호실/테이블입니다.")

    next_id = max([int(item.get("id", 0) or 0) for item in items] + [0]) + 1
    new_item = {
        "id": next_id,
        "date": payload.date,
        "time": payload.time,
        "slot": slot,
        "phone": payload.phone,
        "name": payload.name,
        "count": payload.count,
        "room": payload.room,
        "adult": payload.adult,
        "child": payload.child,
        "infant": payload.infant,
    }
    items.append(new_item)
    _save_tel({"reservations": items})
    if payload.date == _today_str():
        await broadcast_reservations()
    return {"ok": True, "item": new_item}


class TelReservationPatch(BaseModel):
    time: Optional[str] = None
    name: Optional[str] = None
    room: Optional[str] = None
    phone: Optional[str] = None


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


@app.get("/api/display/content")
def api_get_display_content():
    data = _load_display_content()
    try:
        di = int(data.get("default_interval_sec") or 8)
    except (TypeError, ValueError):
        di = 8
    raw_items = data.get("items") or []
    items_out = []
    for it in raw_items:
        row = dict(it)
        url = str(row.get("url") or "")
        filled = _fill_display_name_from_upload_meta(url, str(row.get("name") or ""))
        if filled:
            row["name"] = filled
        items_out.append(row)
    return {
        "items": items_out,
        "default_interval_sec": max(3, min(600, di)),
        "active_slides": _active_display_slides(),
    }


@app.post("/api/display/content")
async def api_set_display_content(payload: DisplayContentIn):
    old_items = list(_load_display_content().get("items") or [])
    normalized: list = []
    for it in payload.items:
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
        entry: dict = {
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
    for idx, d in enumerate(normalized):
        d["id"] = str(idx + 1)
        d["order"] = idx
    try:
        di = int(payload.default_interval_sec)
        di = max(3, min(600, di))
    except (TypeError, ValueError):
        di = 8
    new_urls = {str(d.get("url") or "").strip() for d in normalized}
    _cleanup_removed_display_uploads(old_items, new_urls)
    _save_display_content({"items": normalized, "default_interval_sec": di})
    await broadcast_display_content()
    return {"ok": True, "active_slides": _active_display_slides()}


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
    if not u.startswith("/display/uploads/"):
        return ""
    part = u.split("/")[-1].split("?")[0]
    return _original_name_from_uploaded_file(part)


def _cleanup_removed_display_uploads(old_items: list, new_urls: set) -> None:
    """관리 화면에서 항목이 빠지면 display/uploads 안의 해당 파일·메타도 삭제합니다."""
    base = _display_uploads_dir().resolve()
    for it in old_items:
        url = str(it.get("url") or "").strip()
        if not url or url in new_urls:
            continue
        if not url.startswith("/display/uploads/"):
            continue
        part = url.split("/")[-1].split("?")[0]
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
    """현황판 하단용 이미지·동영상을 display/uploads 에 저장하고 URL 경로를 반환합니다."""
    if not DISPLAY_DIR.exists():
        raise HTTPException(status_code=500, detail="display 폴더를 찾을 수 없습니다.")
    upload_dir = DISPLAY_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    raw_name = (file.filename or "file").replace("\\", "/").split("/")[-1]
    suffix = Path(raw_name).suffix.lower()
    if suffix not in _DISPLAY_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail="허용 확장자: " + ", ".join(sorted(_DISPLAY_UPLOAD_EXTS)),
        )
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    dest = upload_dir / safe_name
    body = await file.read()
    if len(body) > _DISPLAY_UPLOAD_MAX:
        raise HTTPException(status_code=400, detail="파일 크기는 50MB 이하만 가능합니다.")
    dest.write_bytes(body)
    meta_path = upload_dir / f"{safe_name}.meta.json"
    try:
        meta_path.write_text(
            json.dumps({"original_name": raw_name}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return {"url": f"/display/uploads/{safe_name}", "original_name": raw_name}


@app.patch("/api/tel/reservations/{reservation_id}")
async def patch_tel_reservation(reservation_id: int, payload: TelReservationPatch):
    """전화 예약 수정 (admin·당일 현황 연동)."""
    items = _get_tel_reservations()
    idx = next((i for i, x in enumerate(items) if int(x.get("id", 0) or 0) == reservation_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    cur = dict(items[idx])
    new_time = payload.time if payload.time is not None else cur.get("time", "")
    new_room = payload.room if payload.room is not None else cur.get("room", "")
    new_name = payload.name if payload.name is not None else cur.get("name", "")
    new_phone = payload.phone if payload.phone is not None else cur.get("phone", "")
    date = cur.get("date", "")
    for item in items:
        if int(item.get("id", 0) or 0) == reservation_id:
            continue
        if item.get("date") == date and item.get("room") == new_room and _times_overlap(item.get("time", ""), new_time):
            raise HTTPException(status_code=409, detail="기본 식사시간 2시간 기준으로 이미 예약된 호실/테이블입니다.")
    cur["time"] = new_time
    cur["room"] = new_room
    cur["name"] = new_name
    cur["phone"] = new_phone
    cur["slot"] = _time_slot(new_time)
    items[idx] = cur
    _save_tel({"reservations": items})
    if date == _today_str():
        await broadcast_reservations()
    return {"ok": True, "item": cur}


@app.delete("/api/tel/reservations/{reservation_id}")
async def delete_tel_reservation(reservation_id: int):
    """전화 예약 삭제."""
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
    _save_tel({"reservations": kept})
    if removed.get("date") == _today_str():
        await broadcast_reservations()
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
def api_auth_status(role: str):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="잘못된 역할입니다.")
    ns = needs_setup(role)
    needing = list_accounts_needing_setup(role) if ns else []
    fac = first_account_needing_setup(role) if ns else None
    return {
        "needs_setup": ns,
        "role": role,
        "default_account_id": fac,
        "accounts_needing_setup": needing,
    }


@app.get("/api/auth/login-options")
def api_auth_login_options(role: str):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="잘못된 역할입니다.")
    return {"accounts": list_login_options(role)}


@app.get("/api/auth/session")
def api_auth_session(request: Request):
    """유효한 access_token 쿠키가 있으면 역할·계정 정보 반환. 로그인 페이지에서 이미 로그인된 경우 바로 이동할 때 사용."""
    payload = decode_token(extract_token(request))
    if not payload:
        raise HTTPException(status_code=401, detail="인증되지 않았습니다.")
    role = payload.get("role")
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="인증되지 않았습니다.")
    return {
        "ok": True,
        "role": role,
        "account_id": payload.get("sub"),
        "name": payload.get("name"),
    }


@app.post("/api/auth/setup")
def api_auth_setup(body: AuthSetupBody, request: Request):
    try:
        u = set_password_first_time(body.account_id.strip(), body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_token(u["id"], u["role"], u["name"])
    r = JSONResponse({"ok": True, "account_id": u["id"], "role": u["role"]})
    r.set_cookie(**auth_cookie_response(token, request))
    return r


@app.post("/api/auth/login")
def api_auth_login(body: AuthLoginBody, request: Request):
    u = verify_login_account(body.account_id.strip(), body.password)
    if not u:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    token = create_token(u["id"], u["role"], u["name"])
    r = JSONResponse({"ok": True, "account_id": u["id"], "role": u["role"]})
    r.set_cookie(**auth_cookie_response(token, request))
    return r


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    return logout_response(request)


@app.get("/api/auth/accounts")
def api_auth_accounts_list():
    return {"accounts": list_accounts_public()}


@app.post("/api/auth/accounts")
def api_auth_accounts_create(body: AccountCreateIn):
    try:
        account_create(body.id.strip(), body.name, body.role, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.patch("/api/auth/accounts/{account_id}")
def api_auth_accounts_patch(account_id: str, body: AccountPatchIn):
    try:
        account_update(account_id.strip(), name=body.name, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/api/auth/accounts/{account_id}")
def api_auth_accounts_delete(account_id: str):
    try:
        account_delete(account_id.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.post("/api/auth/accounts/{account_id}/revoke")
def api_auth_accounts_revoke(account_id: str):
    try:
        account_revoke(account_id.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok"}


if DISPLAY_DIR.exists():
    app.mount("/display", StaticFiles(directory=str(DISPLAY_DIR), html=True), name="display")
if ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")
if TEL_DIR.exists():
    app.mount("/tel", StaticFiles(directory=str(TEL_DIR), html=True), name="tel")
