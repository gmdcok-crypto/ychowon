"""
Cloudflare R2 (S3 호환 API) — 현황판 하단 광고 파일 업로드.

앱의 ``/api/display/upload`` 는 R2만 사용합니다 (로컬 display/uploads 폴백 없음).

필수 환경 변수:
  R2_ACCOUNT_ID (또는 CLOUDFLARE_ACCOUNT_ID)
  R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
  R2_BUCKET_NAME
  R2_PUBLIC_BASE_URL  — 브라우저가 파일을 불러올 **퍼블릭 URL** (끝 / 없음)
                         예: https://pub-xxxx.r2.dev (버킷 → Public access)
                         **금지:** …r2.cloudflarestorage.com 은 S3 API 주소이며 여기 넣으면 안 됨
                         (API 주소는 R2_S3_ENDPOINT 또는 R2_ACCOUNT_ID 로만 사용)

선택:
  R2_KEY_PREFIX  — 객체 키 접두사 (기본 display-uploads)
  R2_S3_ENDPOINT (또는 R2_ENDPOINT_URL) — S3 API 전체 URL (EU 등). 비우면 자동.
  R2_JURISDICTION=eu — EU 버킷이면 엔드포인트를 *.eu.r2.cloudflarestorage.com 으로 맞춤

버킷·퍼블릭 URL은 Cloudflare 대시보드 R2에서 설정합니다.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional
from urllib.parse import quote, unquote

_logger = logging.getLogger(__name__)


def account_id() -> str:
    return (os.environ.get("R2_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()


def public_base_url() -> str:
    return (os.environ.get("R2_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def _public_url_is_s3_api_host(url: str) -> bool:
    """퍼블릭 URL 자리에 S3 API 엔드포인트를 넣은 경우(흔한 설정 오류)."""
    return "r2.cloudflarestorage.com" in (url or "").strip().lower()


def r2_enabled() -> bool:
    key = (os.environ.get("R2_ACCESS_KEY_ID") or "").strip()
    sec = (os.environ.get("R2_SECRET_ACCESS_KEY") or "").strip()
    bucket = (os.environ.get("R2_BUCKET_NAME") or "").strip()
    pub = public_base_url()
    if not (key and sec and bucket and pub):
        return False
    if _public_url_is_s3_api_host(pub):
        return False
    return bool(s3_endpoint_url())


def r2_missing_env_hints() -> list[str]:
    """업로드 불가 시 어떤 변수가 비었는지 짧게 나열 (관리자 안내용)."""
    missing: list[str] = []
    explicit_ep = (
        os.environ.get("R2_S3_ENDPOINT") or os.environ.get("R2_ENDPOINT_URL") or ""
    ).strip()
    if not account_id() and not explicit_ep:
        missing.append(
            "R2_ACCOUNT_ID(또는 CLOUDFLARE_ACCOUNT_ID) 또는 R2_S3_ENDPOINT(전체 URL)"
        )
    if not (os.environ.get("R2_ACCESS_KEY_ID") or "").strip():
        missing.append("R2_ACCESS_KEY_ID")
    if not (os.environ.get("R2_SECRET_ACCESS_KEY") or "").strip():
        missing.append("R2_SECRET_ACCESS_KEY")
    if not (os.environ.get("R2_BUCKET_NAME") or "").strip():
        missing.append("R2_BUCKET_NAME")
    pub_raw = (os.environ.get("R2_PUBLIC_BASE_URL") or "").strip()
    if pub_raw and _public_url_is_s3_api_host(pub_raw):
        missing.append(
            "R2_PUBLIC_BASE_URL이 S3 API 주소입니다 → R2 버킷 Public access의 "
            "https://pub-….r2.dev 로 바꾸세요(API 주소는 R2_S3_ENDPOINT에만)"
        )
    elif not public_base_url():
        missing.append(
            "R2_PUBLIC_BASE_URL (R2 버킷 퍼블릭 URL, https://pub-….r2.dev , 끝 / 없음)"
        )
    return missing


def r2_upload_unavailable_message() -> str:
    """503 응답·토스트용 한 줄 메시지."""
    parts = r2_missing_env_hints()
    if not parts:
        return "R2 설정을 확인할 수 없습니다."
    return (
        "하단광고 업로드는 R2만 사용합니다. "
        "Railway 등에 다음이 비어 있습니다: "
        + " · ".join(parts)
    )


def key_prefix() -> str:
    p = (os.environ.get("R2_KEY_PREFIX") or "display-uploads").strip().strip("/")
    return p or "display-uploads"


def s3_endpoint_url() -> str:
    """R2 S3 호환 API URL. EU·커스텀 엔드포인트는 환경 변수로 지정."""
    explicit = (
        os.environ.get("R2_S3_ENDPOINT") or os.environ.get("R2_ENDPOINT_URL") or ""
    ).strip()
    if explicit:
        return explicit.rstrip("/")
    aid = account_id()
    if not aid:
        return ""
    jur = (os.environ.get("R2_JURISDICTION") or "").strip().lower()
    if jur in ("eu", "europe", "weur"):
        return f"https://{aid}.eu.r2.cloudflarestorage.com"
    return f"https://{aid}.r2.cloudflarestorage.com"


def _client():
    import boto3
    from botocore.config import Config

    endpoint = s3_endpoint_url()
    if not endpoint:
        raise RuntimeError("R2_ACCOUNT_ID 또는 R2_S3_ENDPOINT 가 필요합니다.")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
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
    bkt = _bucket()
    _client().put_object(**kw)
    base = public_base_url()
    public = f"{base}/{key}"
    _logger.info("R2 put_object ok bucket=%s key=%s url=%s", bkt, key, public)
    # Railway 로그에는 print 가 항상 보이므로 중복 출력(디버깅용)
    print(f"R2 put_object ok bucket={bkt} key={key} url={public}", flush=True)
    return public


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
