"""
지점별 룸·홀 구성.

서버 기동 시 MySQL 연결이 필수이므로, 런타임은 **MySQL의 rooms 설정**만 사용합니다.
(``database_enabled()`` 가 꺼진 예외 경로에서만 ``data/rooms_config*.json`` 폴백 — 마이그레이션·구버전 호환용)

- mchowon: USE_MCHOWON_ROOMS=1, SITE=mchowon, 또는 Railway 이름/도메인에 mchowon 포함.
- data/rooms_config.example.json 은 참고용 복사 템플릿입니다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "rooms_config.json"
EXAMPLE_FILENAME = "rooms_config.example.json"

# load_room_options() 성공 시 사용한 파일명(확장자 .json). 없으면 내장 기본값.
ACTIVE_ROOMS_CONFIG_REF: str | None = None


def build_default_room_options() -> list[dict[str, Any]]:
    """4F룸·5F룸·A~F홀 구조. 모달 탭별 표시용 (기존 main.py와 동일)."""
    opts: list[dict[str, Any]] = []
    for i in range(1, 25):
        opts.append(
            {
                "id": f"4fr{i}",
                "label": f"4F룸 룸{i}",
                "display_label": str(i),
                "type": "room",
                "section": "4F룸",
            }
        )
    for i in range(1, 13):
        opts.append(
            {
                "id": f"5fr{i}",
                "label": f"5F룸 룸{i}",
                "display_label": str(i),
                "type": "room",
                "section": "5F룸",
            }
        )
    for i in range(1, 7):
        opts.append(
            {
                "id": f"a{i}",
                "label": f"A홀 A{i}",
                "display_label": f"A{i}",
                "type": "table",
                "section": "A홀",
            }
        )
    for i in range(1, 10):
        opts.append(
            {
                "id": f"b{i}",
                "label": f"B홀 B{i}",
                "display_label": f"B{i}",
                "type": "table",
                "section": "B홀",
            }
        )
    for i in range(1, 11):
        opts.append(
            {
                "id": f"c{i}",
                "label": f"C홀 C{i}",
                "display_label": f"C{i}",
                "type": "table",
                "section": "C홀",
            }
        )
    d_labels = ["D1"]
    for i in range(2, 9):
        d_labels.append(f"D{i}")
        d_labels.append(f"D{i}(임시)")
    for i in range(9, 12):
        d_labels.append(f"D{i}")
    for idx, dl in enumerate(d_labels):
        opts.append(
            {
                "id": f"d{idx + 1}",
                "label": f"D홀 {dl}",
                "display_label": dl,
                "type": "table",
                "section": "D홀",
            }
        )
    for i in range(1, 10):
        opts.append(
            {
                "id": f"e{i}",
                "label": f"E홀 E{i}",
                "display_label": f"E{i}",
                "type": "table",
                "section": "E홀",
            }
        )
    for i in range(1, 4):
        opts.append(
            {
                "id": f"f{i}",
                "label": f"F홀 F{i}",
                "display_label": f"F{i}",
                "type": "table",
                "section": "F홀",
            }
        )
    return opts


def _normalize_room_entry(raw: dict[str, Any], index: int) -> dict[str, Any] | None:
    label = raw.get("label")
    if label is None or not str(label).strip():
        return None
    label = str(label).strip()
    return {
        "id": str(raw.get("id") if raw.get("id") is not None else f"room{index}"),
        "label": label,
        "display_label": str(raw.get("display_label", label)).strip(),
        "type": str(raw.get("type", "table")).strip(),
        "section": str(raw.get("section", "기타")).strip(),
    }


def _safe_rooms_config_filename(env_val: str | None, default: str) -> str:
    """경로 조작 방지: 파일명(basename)만 허용, .json 만."""
    if env_val is None or not str(env_val).strip():
        return default
    name = Path(str(env_val).strip()).name
    if not name.endswith(".json"):
        return default
    return name


def _is_mchowon_context() -> bool:
    """mchowon 지점 배포로 볼지 여부."""
    flag = (os.environ.get("USE_MCHOWON_ROOMS") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    site = (os.environ.get("SITE") or os.environ.get("BRANCH_SITE") or "").strip().lower()
    if site == "mchowon":
        return True
    svc = (os.environ.get("RAILWAY_SERVICE_NAME") or os.environ.get("RAILWAY_SERVICE") or "").lower()
    if "mchowon" in svc:
        return True
    for key in (
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_STATIC_URL",
        "RAILWAY_SERVICE_DOMAIN",
        "RAILWAY_ENVIRONMENT_NAME",
    ):
        if "mchowon" in (os.environ.get(key) or "").lower():
            return True
    return "mchowon" in (os.environ.get("HOSTNAME") or "").lower()


MCHOWON_ROOMS_FILE = "rooms_config.mchowon.json"


def _pick_rooms_config_filename(data_dir: Path) -> str:
    """
    어떤 논리 파일명( DB 키 / data/*.json )을 쓸지 결정.

    DB 모드: 디스크 존재 여부는 보지 않음 — ROOMS_CONFIG_FILE → mchowon 이면 mchowon 키 → 기본 키.
    파일 모드: ROOMS_CONFIG_FILE → data 의 mchowon.json 존재 → rooms_config.json 존재 → 기본 키.
    """
    env_raw = os.environ.get("ROOMS_CONFIG_FILE")
    if env_raw and str(env_raw).strip():
        return _safe_rooms_config_filename(env_raw, CONFIG_FILENAME)

    try:
        from db_config import database_enabled

        if database_enabled():
            if _is_mchowon_context():
                return MCHOWON_ROOMS_FILE
            return CONFIG_FILENAME
    except Exception:
        pass

    mchowon_path = data_dir / MCHOWON_ROOMS_FILE
    if _is_mchowon_context() and mchowon_path.exists():
        return MCHOWON_ROOMS_FILE

    if (data_dir / CONFIG_FILENAME).exists():
        return CONFIG_FILENAME

    return CONFIG_FILENAME


def load_room_options(data_dir: Path) -> list[dict[str, Any]]:
    global ACTIVE_ROOMS_CONFIG_REF
    fname = _pick_rooms_config_filename(data_dir)
    path = data_dir / fname
    ACTIVE_ROOMS_CONFIG_REF = None

    from db_config import database_enabled
    from db_repo import load_rooms_config_file

    data = None
    if database_enabled():
        picked = fname
        try:
            data = load_rooms_config_file(fname)
            if data is None and fname == MCHOWON_ROOMS_FILE:
                data = load_rooms_config_file(CONFIG_FILENAME)
                if data is not None:
                    fname = CONFIG_FILENAME
        except Exception:
            data = None
        if data is None:
            if picked == MCHOWON_ROOMS_FILE:
                print(
                    "  경고: MySQL에 룸·홀 설정 없음 (%s 또는 %s) — 내장 기본 룸 구성 사용"
                    % (MCHOWON_ROOMS_FILE, CONFIG_FILENAME)
                )
            else:
                print(
                    "  경고: MySQL에 룸·홀 설정 없음 (%s) — 내장 기본 룸 구성 사용" % picked
                )
            return build_default_room_options()
    else:
        if not path.exists():
            if os.environ.get("ROOMS_CONFIG_FILE"):
                print("  경고: data/%s 없음 — 내장 기본 룸 구성 사용" % fname)
            return build_default_room_options()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print("  경고: %s JSON 파싱 실패 — 기본 룸 구성 사용 (%s)" % (fname, e))
            return build_default_room_options()

    rooms = data.get("rooms") if isinstance(data, dict) else data
    if not isinstance(rooms, list):
        print("  경고: %s 에 'rooms' 배열이 없음 — 기본 룸 구성 사용" % fname)
        return build_default_room_options()

    out: list[dict[str, Any]] = []
    for i, r in enumerate(rooms):
        if not isinstance(r, dict):
            continue
        norm = _normalize_room_entry(r, i)
        if norm:
            out.append(norm)
    if not out:
        print("  경고: %s 에 유효한 룸이 없음 — 기본 룸 구성 사용" % fname)
        return build_default_room_options()
    ACTIVE_ROOMS_CONFIG_REF = fname
    return out


def ensure_example_file(data_dir: Path) -> None:
    """예시 파일이 없으면 생성(복사용)."""
    ex = data_dir / EXAMPLE_FILENAME
    if ex.exists():
        return
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "description": "이 파일을 rooms_config.json 으로 복사한 뒤 지점에 맞게 rooms 배열을 수정하세요.",
            "rooms": build_default_room_options(),
        }
        with open(ex, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
