import io
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.lab import LabParameter, LabSample, LabSamplePoint


def _as(role: str, uid: int = 7):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_preview_suggests_mapping(client, db_session):
    db_session.add(LabParameter(code="PH", name="pH"))
    await db_session.commit()
    _as("operator")
    content = _xlsx([["time", "pH"], ["2026-06-27T09:00:00", "7.2"]])
    resp = await client.post(
        "/api/lab/import/preview",
        files={
            "file": (
                "lab.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["headers"] == ["time", "pH"]
    # "pH" header maps to the PH parameter
    ph = (await db_session.execute(select(LabParameter))).scalars().first()
    assert body["suggestions"]["pH"] == ph.id
    assert body["suggestions"]["time"] is None


@pytest.mark.asyncio
async def test_commit_imports_rows(client, db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH")
    db_session.add_all([point, param])
    await db_session.commit()
    await db_session.refresh(point)
    await db_session.refresh(param)
    _as("operator")
    resp = await client.post(
        "/api/lab/import/commit",
        json={
            "sample_point_id": point.id,
            "time_column": "time",
            "headers": ["time", "pH"],
            "mapping": {"pH": param.id},
            "rows": [
                ["2026-06-27T09:00:00", "7.2"],
                ["2026-06-27T12:00:00", "7.4"],
                ["bad-date", "9.9"],
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 2
    assert len(body["errors"]) == 1
    samples = (await db_session.execute(select(LabSample))).scalars().all()
    assert len(samples) == 2
