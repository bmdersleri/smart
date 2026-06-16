from io import BytesIO

import pytest
import pytest_asyncio
from openpyxl import Workbook

from app.api.auth import get_current_user
from app.main import app
from app.models.tag import Tag


def _template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK 2026"
    ws["D2"] = "SENSÖR KODLARI"
    ws["E2"] = "410BF103"
    ws["E1"] = "DEBİ m3/gün"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "admin"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    yield
    from sqlalchemy import delete

    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn

    await db_session.execute(delete(ExcelTemplateColumn))
    await db_session.execute(delete(ExcelTemplate))
    await db_session.execute(delete(Tag))
    await db_session.commit()


@pytest_asyncio.fixture
async def seeded_tag(db_session):
    tag = Tag(node_id="a", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    return tag


@pytest.mark.asyncio
async def test_inspect_returns_proposal(client, seeded_tag):
    resp = await client.post(
        "/api/excel-templates/inspect",
        files={
            "file": (
                "t.xlsx",
                _template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sheet_name"] == "OCAK 2026"
    assert data["columns"][0]["source_code"] == "410BF103"


@pytest.mark.asyncio
async def test_save_and_generate_roundtrip(client, seeded_tag):
    import base64

    payload = {
        "name": "Balta",
        "description": "",
        "file_b64": base64.b64encode(_template_bytes()).decode(),
        "sheet_name": "OCAK 2026",
        "header_row": 2,
        "date_col": "D",
        "data_start_row": 3,
        "date_mode": "write",
        "columns": [
            {
                "col_letter": "E",
                "tag_id": seeded_tag.id,
                "agg": "sum",
                "source_code": "410BF103",
                "enabled": True,
            }
        ],
    }
    save = await client.post("/api/excel-templates", json=payload)
    assert save.status_code == 201, save.text
    tpl_id = save.json()["id"]

    listed = await client.get("/api/excel-templates")
    assert any(t["id"] == tpl_id for t in listed.json())

    gen = await client.post(f"/api/excel-templates/{tpl_id}/generate?year=2026&month=1")
    assert gen.status_code == 200
    assert gen.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert gen.content[:2] == b"PK"
