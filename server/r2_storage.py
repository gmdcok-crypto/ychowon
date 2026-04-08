"""
Cloudflare R2 (S3 호환 API) — 현황판 하단 광고 파일 업로드.

앱의 ``/api/display/upload`` 는 R2만 사용합니다 (로컬 display/uploads 폴백 없음).

필수 환경 변수:
  R2_ACCOUNT_ID (또는 CLOUDFLARE_ACCOUNT_ID)
  R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
  R2_BUCKET_NAME
  R2_PUBLIC_BASE_URL  — 퍼블릭 접근 URL 접두사 (끝 슬래시 없음)
                         예: https://pub-xxxx.r2.dev 또는 커스텀 도메인

선택:
  R2_KEY_PREFIX  — 객체 키 접두사 (기본 display-uploads)

버킷·퍼블릭 URL은 Cloudflare 대시보드 R2에서 설정합니다.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional
from urllib.parse import quote, unquote


def account_id() -> str:
    return (os.environ.get("R2_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()


def public_base_url() -> str:
    return (os.environ.get("R2_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def r2_enabled() -> bool:
    key = (os.environ.get("R2_ACCESS_KEY_ID") or "").strip()
    sec = (os.environ.get("R2_SECRET_ACCESS_KEY") or "").strip()
    bucket = (os.environ.get("R2_BUCKET_NAME") or "").strip()
    return bool(account_id() and key and sec and bucket and public_base_url())


def key_prefix() -> str:
    p = (os.environ.get("R2_KEY_PREFIX") or "display-uploads").strip().strip("/")
    return p or "display-uploads"


def _client():
    import boto3
    from botocore.config import Config

    aid = account_id()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{aid}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _bucket() -> str:
    return os.environ["R2_BUCKET_NAME"].strip()


def _content_type_for_suffix(suffix: str) -> Optional[str]:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
    }.get(suffix.lower())


def upload_display_bytes(
    body: bytes,
    suffix: str,
    original_name: str,
) -> str:
    """바이트를 R2에 올리고 브라우저용 퍼블릭 URL을 반환합니다."""
    key = f"{key_prefix()}/{uuid.uuid4().hex}{suffix}"
    ct = _content_type_for_suffix(suffix)
    meta_val = quote(original_name or "", safe="")
    kw: dict = {
        "Bucket": _bucket(),
        "Key": key,
        "Body": body,
        "Metadata": {"original-name": meta_val},
    }
    if ct:
        kw["ContentType"] = ct
    _client().put_object(**kw)
    base = public_base_url()
    return f"{base}/{key}"


def is_r2_public_url(url: str) -> bool:
    u = (url or "").strip().split("?")[0]
    base = public_base_url()
    return bool(base and u.startswith(base + "/"))


def object_key_from_public_url(url: str) -> str:
    base = public_base_url()
    u = (url or "").strip().split("?")[0]
    if not base or not u.startswith(base + "/"):
        return ""
    return u[len(base) + 1 :]


def delete_object_by_public_url(url: str) -> None:
    key = object_key_from_public_url(url)
    if not key or ".." in key:
        return
    try:
        _client().delete_object(Bucket=_bucket(), Key=key)
    except Exception:
        pass


def head_original_name(url: str) -> str:
    """HeadObject로 업로드 시 넣은 original-name 메타데이터를 읽습니다."""
    key = object_key_from_public_url(url)
    if not key:
        return ""
    try:
        r = _client().head_object(Bucket=_bucket(), Key=key)
        meta = r.get("Metadata") or {}
        raw = meta.get("original-name") or meta.get("original_name") or ""
        if not raw:
            return ""
        return unquote(str(raw), encoding="utf-8", errors="replace").strip()[:200]
    except Exception:
        return ""
