"""Upload size and content guardrails for file-like inputs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status

from app.core.config import settings

_ZIP_MAGIC = b"PK\x03\x04"
_JWT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class UploadFileLike(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def normalize_upload_extension(filename: str | None) -> str:
    """Return a normalized lowercase extension, or ``""`` when absent."""
    if not filename:
        return ""
    suffix = Path(filename.strip()).suffix.lower()
    if suffix == ".xlsm":
        return ".xlsx"
    return suffix


async def read_upload_bytes(file: UploadFileLike, *, limit: int, kind: str) -> bytes:
    """Read at most ``limit + 1`` bytes and reject oversized uploads."""
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{kind} dosyası çok büyük",
        )
    return data


def assert_xlsx_payload(data: bytes) -> bytes:
    """Validate XLSX zip magic."""
    if not data.startswith(_ZIP_MAGIC):
        raise HTTPException(status_code=400, detail="Geçersiz XLSX içeriği")
    return data


def assert_csv_payload(data: bytes) -> bytes:
    """Validate CSV text payloads, allowing UTF-8 text as the fallback."""
    if not data:
        raise HTTPException(status_code=400, detail="CSV dosyası boş olamaz")
    if b"\x00" in data:
        raise HTTPException(status_code=400, detail="Geçersiz CSV içeriği")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz CSV içeriği") from exc
    return data


def assert_license_payload(data: bytes) -> bytes:
    """Validate license text that looks like a JWT compact serialization."""
    if not data:
        raise HTTPException(status_code=400, detail="Lisans dosyası boş olamaz")
    try:
        token = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz lisans içeriği") from exc
    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise HTTPException(status_code=400, detail="Geçersiz lisans içeriği")
    if any(_JWT_SEGMENT_RE.fullmatch(part) is None for part in parts):
        raise HTTPException(status_code=400, detail="Geçersiz lisans içeriği")
    return data


async def read_xlsx_upload(file: UploadFileLike) -> bytes:
    data = await read_upload_bytes(file, limit=settings.UPLOAD_MAX_XLSX_BYTES, kind="XLSX")
    return assert_xlsx_payload(data)


async def read_csv_upload(file: UploadFileLike) -> bytes:
    data = await read_upload_bytes(file, limit=settings.UPLOAD_MAX_CSV_BYTES, kind="CSV")
    return assert_csv_payload(data)


async def read_license_upload(file: UploadFileLike) -> bytes:
    data = await read_upload_bytes(file, limit=settings.UPLOAD_MAX_LICENSE_BYTES, kind="Lisans")
    return assert_license_payload(data)


def ensure_template_b64_size(file_b64: str) -> str:
    """Reject oversized template payloads before decoding."""
    if len(file_b64.encode("utf-8")) > settings.UPLOAD_MAX_TEMPLATE_B64_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Şablon verisi çok büyük",
        )
    return file_b64
