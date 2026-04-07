"""
JWT + bcrypt(직접 사용). 계정은 accounts[] (id, name, role, password_hash).
역할(role): admin / display / tel — 권한 판별에 사용.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import bcrypt
import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

ROLES = ("admin", "display", "tel")
SYSTEM_IDS = frozenset({"admin", "display", "tel"})
ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")

COOKIE_NAME = "access_token"
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = 30

DEFAULT_NAMES = {
    "admin": "관리자",
    "display": "현황판",
    "tel": "전화예약",
}

# bcrypt: UTF-8로 인코딩한 뒤 최대 72바이트만 사용(알고리즘 한계). 글자 수가 아니라 바이트 기준.
# 특수문자·한글·이모지 제한은 없음. 다만 한 글자가 여러 바이트면 같은 글자 수라도 더 빨리 72바이트에 도달함.
# passlib은 bcrypt 4.x와 조합 시 내부에서 동일 오류가 나는 경우가 있어, bcrypt를 직접 사용한다.
BCRYPT_PASSWORD_MAX_BYTES = 72
BCRYPT_ROUNDS = 12


def _password_bytes_for_bcrypt(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_PASSWORD_MAX_BYTES]


def _hash_password(password: str) -> str:
    b = _password_bytes_for_bcrypt(password)
    return bcrypt.hashpw(b, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _verify_password(password: str, stored_hash: Any) -> bool:
    if not stored_hash or not isinstance(stored_hash, str):
        return False
    b = _password_bytes_for_bcrypt(password)
    try:
        return bcrypt.checkpw(b, stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


_data_dir: Optional[Path] = None
_auth_file: Optional[Path] = None
_secret_file: Optional[Path] = None


def configure(data_dir: Path) -> None:
    global _data_dir, _auth_file, _secret_file
    _data_dir = data_dir
    _auth_file = data_dir / "auth.json"
    _secret_file = data_dir / ".jwt_secret"
    _ensure_auth_file()


def _ensure_auth_file() -> None:
    assert _auth_file is not None
    if not _auth_file.is_file():
        accs = [
            {"id": "admin", "name": DEFAULT_NAMES["admin"], "role": "admin", "password_hash": None},
            {"id": "display", "name": DEFAULT_NAMES["display"], "role": "display", "password_hash": None},
            {"id": "tel", "name": DEFAULT_NAMES["tel"], "role": "tel", "password_hash": None},
        ]
        _auth_file.write_text(json.dumps({"accounts": accs}, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate_passwords_to_accounts(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("accounts"), list) and raw["accounts"]:
        return raw
    passwords = raw.get("passwords") or {}
    accounts = []
    for rid in ROLES:
        accounts.append(
            {
                "id": rid,
                "name": DEFAULT_NAMES.get(rid, rid),
                "role": rid,
                "password_hash": passwords.get(rid),
            }
        )
    return {"accounts": accounts}


def _load_store() -> dict[str, Any]:
    assert _auth_file is not None
    _ensure_auth_file()
    try:
        raw = json.loads(_auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    merged = _migrate_passwords_to_accounts(raw)
    if merged != raw and _auth_file.is_file():
        _save_store(merged)
    return merged


def _save_store(data: dict[str, Any]) -> None:
    assert _auth_file is not None
    _auth_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _accounts_list(store: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    s = store if store is not None else _load_store()
    accs = s.get("accounts")
    if not isinstance(accs, list):
        return []
    return accs


def _find_account_by_id(aid: str) -> Optional[dict[str, Any]]:
    for a in _accounts_list():
        if str(a.get("id")) == aid:
            return a
    return None


def _jwt_secret() -> str:
    env = (os.environ.get("JWT_SECRET") or "").strip()
    if env:
        return env
    assert _secret_file is not None
    if _secret_file.is_file():
        return _secret_file.read_text(encoding="utf-8").strip()
    import secrets

    s = secrets.token_hex(32)
    _secret_file.write_text(s, encoding="utf-8")
    return s


def needs_setup(role: str) -> bool:
    """해당 역할로 로그인 가능한 계정이 하나도 없으면 True (비밀번호 설정 전)."""
    if role not in ROLES:
        return False
    for a in _accounts_list():
        if a.get("role") == role and a.get("password_hash"):
            return False
    return True


def list_accounts_public() -> list[dict[str, Any]]:
    """관리 화면용: 해시 제외."""
    out = []
    for i, a in enumerate(_accounts_list()):
        h = a.get("password_hash")
        out.append(
            {
                "no": i + 1,
                "id": a.get("id"),
                "name": a.get("name") or "",
                "role": a.get("role"),
                "authenticated": bool(h),
            }
        )
    return out


def list_login_options(role: str) -> list[dict[str, str]]:
    """로그인 선택용: 비밀번호가 있는 계정만."""
    if role not in ROLES:
        return []
    return [
        {"id": str(a.get("id")), "name": str(a.get("name") or a.get("id"))}
        for a in _accounts_list()
        if a.get("role") == role and a.get("password_hash")
    ]


def set_password_first_time(account_id: str, password: str) -> dict[str, str]:
    a = _find_account_by_id(account_id)
    if not a:
        raise ValueError("계정을 찾을 수 없습니다.")
    if a.get("password_hash"):
        raise ValueError("이미 비밀번호가 설정되었습니다.")
    store = _load_store()
    accs = _accounts_list(store)
    out = None
    for row in accs:
        if str(row.get("id")) == account_id:
            row["password_hash"] = _hash_password(password)
            out = row
            break
    if not out:
        raise ValueError("계정을 찾을 수 없습니다.")
    store["accounts"] = accs
    _save_store(store)
    return {
        "id": str(out["id"]),
        "role": str(out["role"]),
        "name": str(out.get("name") or out["id"]),
    }


def first_account_needing_setup(role: str) -> Optional[str]:
    """해당 역할에서 비밀번호가 없는 첫 계정 id (로그인 화면 기본 선택)."""
    for a in _accounts_list():
        if a.get("role") == role and not a.get("password_hash"):
            return str(a.get("id"))
    return None


def list_accounts_needing_setup(role: str) -> list[dict[str, str]]:
    """해당 역할에서 비밀번호 미설정 계정 (최초 설정 화면 드롭다운용)."""
    if role not in ROLES:
        return []
    out = []
    for a in _accounts_list():
        if a.get("role") == role and not a.get("password_hash"):
            aid = str(a.get("id"))
            out.append({"id": aid, "name": str(a.get("name") or aid)})
    return out


def verify_login_account(account_id: str, password: str) -> Optional[dict[str, Any]]:
    a = _find_account_by_id(account_id)
    if not a:
        return None
    h = a.get("password_hash")
    if not h:
        return None
    if not _verify_password(password, h):
        return None
    return {"id": str(a["id"]), "role": str(a["role"]), "name": str(a.get("name") or a["id"])}


def create_token(account_id: str, role: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": account_id,
        "role": role,
        "name": name,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)


def decode_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def extract_token(request: Request) -> Optional[str]:
    c = request.cookies.get(COOKIE_NAME)
    if c:
        return c
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def role_from_request(request: Request) -> Optional[str]:
    payload = decode_token(extract_token(request))
    if not payload:
        return None
    r = payload.get("role")
    if r in ROLES:
        return str(r).strip()
    return None


def login_redirect_for(path: str) -> str:
    if path.startswith("/admin"):
        return "/admin/login.html"
    if path.startswith("/display"):
        return "/display/login.html"
    if path.startswith("/tel"):
        return "/tel/login.html"
    return "/display/login.html"


def is_public_auth_api_path(path: str) -> bool:
    if path in ("/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/logout", "/api/auth/session"):
        return True
    if path.startswith("/api/auth/login-options"):
        return True
    return False


def is_public_path(path: str) -> bool:
    if is_public_auth_api_path(path):
        return True
    if path in ("/api/health", "/favicon.ico", "/sw.js"):
        return True
    if path in ("/admin/login.html", "/display/login.html", "/tel/login.html"):
        return True
    if path in ("/tel/manifest.json", "/tel/sw.js", "/display/manifest.json", "/display/sw.js"):
        return True
    if path.startswith("/display/icon-") or path == "/display/manifest.json":
        return True
    # 하단광고 업로드 파일: URL이 긴 난수라 추측 어렵고, img 태그는 동일 출처 쿠키 이슈가 있어 공개
    if path.startswith("/display/uploads/"):
        return True
    return False


def static_allows(path: str, role: Optional[str]) -> bool:
    if not role:
        return False
    if role == "admin":
        return True
    if path.startswith("/admin/"):
        return role == "admin"
    if path.startswith("/display/"):
        return role == "display"
    if path.startswith("/tel/"):
        return role == "tel"
    return False


def api_allows(path: str, method: str, role: Optional[str]) -> bool:
    # 프록시/클라이언트에 따라 끝에 / 가 붙는 경우가 있어 통일
    p = path.rstrip("/") or "/"
    if is_public_auth_api_path(p) or p == "/api/health":
        return True

    # 현황판 TV·키오스크: 당일 목록·하단광고 조회는 비로그인 허용 (쿠키 없음·401 반복 방지)
    if method == "GET" and p.startswith("/api/reservations/today"):
        return True
    if method == "GET" and p == "/api/display/content":
        return True

    if p == "/api/branches":
        if method == "GET":
            return role in ("admin", "display", "tel")
        if method == "POST":
            return role == "admin"
        return False
    if p.startswith("/api/auth/accounts"):
        return role == "admin"
    if not role:
        return False

    # 현황판 하단: 업로드·목록 저장은 관리자·현황판 계정
    if p.startswith("/api/display"):
        if p == "/api/display/upload" or (p == "/api/display/content" and method == "POST"):
            return role in ("admin", "display")
        if role == "admin":
            return True
        return role == "display"

    if role == "admin":
        return True
    if p.startswith("/api/reservations/today"):
        return False
    if p.startswith("/api/tel/"):
        return role == "tel"
    return False


async def auth_middleware(request: Request, call_next) -> Response:
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    token_role = role_from_request(request)

    if is_public_path(path):
        return await call_next(request)

    if path.startswith("/api/"):
        if api_allows(path, request.method, token_role):
            return await call_next(request)
        return JSONResponse({"detail": "인증이 필요합니다."}, status_code=401)

    if path == "/" or path == "/display":
        if not token_role:
            return RedirectResponse(url="/display/login.html", status_code=302)
        if token_role == "tel":
            return RedirectResponse(url="/tel/", status_code=302)
        if token_role in ("admin", "display"):
            return await call_next(request)
        return RedirectResponse(url="/display/login.html", status_code=302)

    if path.startswith("/admin/") or path.startswith("/display/") or path.startswith("/tel/"):
        if static_allows(path, token_role):
            return await call_next(request)
        return RedirectResponse(url=login_redirect_for(path), status_code=302)

    return await call_next(request)


def ws_role_allowed(websocket) -> bool:
    token = websocket.cookies.get(COOKIE_NAME)
    payload = decode_token(token)
    if not payload:
        return True
    role = payload.get("role")
    return role in ("admin", "display")


def auth_cookie_response(token: str, request: Request) -> dict[str, Any]:
    secure = request.url.scheme == "https" or bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    return {
        "key": COOKIE_NAME,
        "value": token,
        "httponly": True,
        "max_age": 60 * 60 * 24 * JWT_EXPIRE_DAYS,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
    }


def logout_response(request: Request) -> JSONResponse:
    secure = request.url.scheme == "https" or bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="lax")
    return r


# --- 계정 CRUD (관리자 전용, main에서 호출) ---


def account_create(aid: str, name: str, role: str, password: str) -> dict[str, Any]:
    if not ID_RE.match(aid):
        raise ValueError("계정 ID는 영문 시작, 영숫자·_- 만 2~64자")
    if role not in ROLES:
        raise ValueError("잘못된 역할")
    if _find_account_by_id(aid):
        raise ValueError("이미 있는 계정 ID입니다.")
    store = _load_store()
    accs = _accounts_list(store)
    accs.append(
        {
            "id": aid,
            "name": name.strip() or aid,
            "role": role,
            "password_hash": _hash_password(password),
        }
    )
    store["accounts"] = accs
    _save_store(store)
    return {"id": aid, "name": name, "role": role}


def account_update(aid: str, name: Optional[str] = None, password: Optional[str] = None) -> None:
    store = _load_store()
    accs = _accounts_list(store)
    for row in accs:
        if str(row.get("id")) == aid:
            if name is not None:
                row["name"] = name.strip() or row.get("id")
            if password is not None:
                row["password_hash"] = _hash_password(password)
            store["accounts"] = accs
            _save_store(store)
            return
    raise ValueError("계정을 찾을 수 없습니다.")


def account_delete(aid: str) -> None:
    if aid in SYSTEM_IDS:
        raise ValueError("기본 계정(admin, display, tel)은 삭제할 수 없습니다. 인증 취소만 가능합니다.")
    store = _load_store()
    accs = [a for a in _accounts_list(store) if str(a.get("id")) != aid]
    if len(accs) == len(_accounts_list(store)):
        raise ValueError("계정을 찾을 수 없습니다.")
    store["accounts"] = accs
    _save_store(store)


def account_revoke(aid: str) -> None:
    """비밀번호 제거 → 다음 로그인 시 재설정(또는 관리자가 비번 재설정)."""
    store = _load_store()
    accs = _accounts_list(store)
    for row in accs:
        if str(row.get("id")) == aid:
            row["password_hash"] = None
            store["accounts"] = accs
            _save_store(store)
            return
    raise ValueError("계정을 찾을 수 없습니다.")
