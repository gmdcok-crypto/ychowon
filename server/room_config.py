"""
지점별 룸·홀 구성.

- 기본: data/rooms_config.json 이 있으면 해당 목록을 사용합니다.
- 환경 변수 ROOMS_CONFIG_FILE 로 다른 파일명을 지정할 수 있습니다.
  예: ROOMS_CONFIG_FILE=rooms_config.mchowon.json (레포의 data/ 아래 파일)
- 파일이 없거나 오류 시 아래 내장 기본값(초원농원 구조)을 사용합니다.
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


def load_room_options(data_dir: Path) -> list[dict[str, Any]]:
    global ACTIVE_ROOMS_CONFIG_REF
    fname = _safe_rooms_config_filename(os.environ.get("ROOMS_CONFIG_FILE"), CONFIG_FILENAME)
    path = data_dir / fname
    ACTIVE_ROOMS_CONFIG_REF = None

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
