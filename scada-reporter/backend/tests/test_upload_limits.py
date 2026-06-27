import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.upload_limits import (
    ensure_template_b64_size,
    normalize_upload_extension,
    read_csv_upload,
    read_license_upload,
    read_xlsx_upload,
)


def _upload(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename)


@pytest.fixture
def _small_limits(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_XLSX_BYTES", 32)
    monkeypatch.setattr(settings, "UPLOAD_MAX_CSV_BYTES", 32)
    monkeypatch.setattr(settings, "UPLOAD_MAX_LICENSE_BYTES", 64)
    monkeypatch.setattr(settings, "UPLOAD_MAX_TEMPLATE_B64_BYTES", 8)


def test_normalize_upload_extension_handles_case_and_aliases():
    assert normalize_upload_extension("Report.XLSX") == ".xlsx"
    assert normalize_upload_extension("Report.XLSM") == ".xlsx"
    assert normalize_upload_extension("Report.CSV") == ".csv"
    assert normalize_upload_extension(None) == ""


@pytest.mark.asyncio
async def test_read_xlsx_upload_accepts_valid_small_payload(_small_limits):
    file = _upload("report.XLSX", b"PK\x03\x04hello")

    data = await read_xlsx_upload(file)

    assert data == b"PK\x03\x04hello"


@pytest.mark.asyncio
async def test_read_csv_upload_rejects_oversized_payload(_small_limits):
    file = _upload("tags.csv", b"a" * 33)

    with pytest.raises(HTTPException) as excinfo:
        await read_csv_upload(file)

    assert excinfo.value.status_code == 413


@pytest.mark.asyncio
async def test_read_xlsx_upload_rejects_wrong_magic_bytes(_small_limits):
    file = _upload("report.xlsx", b"not-zip")

    with pytest.raises(HTTPException) as excinfo:
        await read_xlsx_upload(file)

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_read_csv_upload_accepts_text_payload(_small_limits):
    file = _upload("tags.csv", b"name,value\nA,1\n")

    data = await read_csv_upload(file)

    assert data == b"name,value\nA,1\n"


@pytest.mark.asyncio
async def test_read_csv_upload_rejects_binary_content(_small_limits):
    with pytest.raises(HTTPException) as excinfo:
        await read_csv_upload(_upload("tags.csv", b"\x00\x01\x02"))

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_read_license_upload_accepts_jwt_like_payload(_small_limits):
    file = _upload("license.jwt", b"eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln")

    data = await read_license_upload(file)

    assert data == b"eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"


@pytest.mark.asyncio
async def test_read_license_upload_rejects_wrong_shape(_small_limits):
    file = _upload("license.jwt", b"not-a-jwt")

    with pytest.raises(HTTPException) as excinfo:
        await read_license_upload(file)

    assert excinfo.value.status_code == 400


def test_template_b64_limit_rejects_oversized_text(_small_limits):
    with pytest.raises(HTTPException) as excinfo:
        ensure_template_b64_size("123456789")

    assert excinfo.value.status_code == 413
