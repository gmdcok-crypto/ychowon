"""
역할별 JWT + bcrypt 비밀번호 (admin / display / tel).
최초 접속 시 비밀번호 미설정이면 /api/auth/setup 으로 1회 설정.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import jwt
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

ROLES = ("admin", "display", "tel")
COOKIE_NAME = "access_token"
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        _auth_file.write_text(
            json.dumps({"passwords": {r: None for r in ROLES}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _load_store() -> dict[str, Any]:
    assert _auth_file is not None
    _ensure_auth_file()
    try:
        return json.loads(_auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"passwords": {r: None for r in ROLES}}


def _save_store(data: dict[str, Any]) -> None:
    assert _auth_file is not None
    _auth_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    if role not in ROLES:
        return False
    pw = (_load_store().get("passwords") or {}).get(role)
    return pw is None or pw == ""


def set_password(role: str, password: str) -> None:
    if role not in ROLES:
        raise ValueError("invalid role")
    if len(password) < 4:
        raise ValueError("password too short")
    store = _load_store()
    passwords = dict(store.get("passwords") or {})
    if passwords.get(role):
        raise ValueError("already set")
    passwords[role] = pwd_context.hash(password)
    store["passwords"] = passwords
    _save_store(store)


def change_password(role: str, old: str, new: str) -> None:
    if role not in ROLES:
        raise ValueError("invalid role")
    store = _load_store()
    h = (store.get("passwords") or {}).get(role)
    if not h or not pwd_context.verify(old, h):
        raise ValueError("wrong password")
    store.setdefault("passwords", {})[role] = pwd_context.hash(new)
    _save_store(store)


def verify_login(role: str, password: str) -> bool:
    if role not in ROLES:
        return False
    h = (_load_store().get("passwords") or {}).get(role)
    if not h:
        return False
    return pwd_context.verify(password, h)


def create_token(role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": role,
        "role": role,
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
    r = payload.get("role") or payload.get("sub")
    if r in ROLES:
        return str(r)
    return None


def login_redirect_for(path: str) -> str:
    if path.startswith("/admin"):
        return "/admin/login.html"
    if path.startswith("/display"):
        return "/display/login.html"
    if path.startswith("/tel"):
        return "/tel/login.html"
    return "/display/login.html"


def is_public_path(path: str) -> bool:
    if path.startswith("/api/auth/"):
        return True
    if path in ("/api/health", "/favicon.ico", "/sw.js"):
        return True
    if path in ("/admin/login.html", "/display/login.html", "/tel/login.html"):
        return True
    # PWA (비로그인 설치·SW — 본 화면은 여전히 로그인 필요)
    if path in ("/tel/manifest.json", "/tel/sw.js", "/display/manifest.json", "/display/sw.js"):
        return True
    if path.startswith("/display/icon-") or path == "/display/manifest.json":
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
    if path.startswith("/api/auth/") or path == "/api/health":
        return True
    if not role:
        return False
    if role == "admin":
        return True
    if path.startswith("/api/reservations/today"):
        if method == "GET":
            return role == "display"
        return False
    if path.startswith("/api/tel/"):
        return role == "tel"
    if path.startswith("/api/display/"):
        if path == "/api/display/upload" or (path == "/api/display/content" and method == "POST"):
            return False
        return role == "display"
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
    """WebSocket: admin·display 만 (현황판·관리 실시간)."""
    token = websocket.cookies.get(COOKIE_NAME)
    payload = decode_token(token)
    if not payload:
        return False
    role = payload.get("role") or payload.get("sub")
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
