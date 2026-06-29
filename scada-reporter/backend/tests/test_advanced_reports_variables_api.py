"""Advanced report templates round-trip selected facility variable ids."""

import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.facility_variable import FacilityVariable
from app.models.report_archive import ReportArchive
from app.models.report_template import ReportTemplate
from app.models.tag import Tag, TagReading
from app.models.user import User


async def _admin_token(client: AsyncClient, db: AsyncSession, username: str) -> str:
    db.add(
        User(
            username=username,
            email=f"{username}@t.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_template_roundtrips_variable_ids(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "var_user1")
    headers = {"Authorization": f"Bearer {tok}"}
    body = {
        "name": "VarTemplate",
        "tag_ids": [],
        "variable_ids": [11, 22],
        "output_format": "json",
    }
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    tid = resp.json()["id"]
    assert resp.json()["variable_ids"] == [11, 22]

    got = await client.get(f"/api/advanced-reports/templates/{tid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["variable_ids"] == [11, 22]


@pytest.mark.asyncio
async def test_template_variable_ids_default_empty(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "var_user2")
    headers = {"Authorization": f"Bearer {tok}"}
    body = {"name": "NoVars", "tag_ids": [1], "output_format": "json"}
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["variable_ids"] == []


@pytest.mark.asyncio
async def test_archive_get_exposes_variable_refs(client: AsyncClient, db_session: AsyncSession):
    """Arşiv GET yanıtı variable_refs_json'u variable_refs olarak açığa çıkarmalı."""
    from app.services.report_generator import generate_report_from_template

    tok = await _admin_token(client, db_session, "vr_user3")
    headers = {"Authorization": f"Bearer {tok}"}

    # Tag ve okumalar oluştur
    tag = Tag(node_id="ns=2;s=ApiVG2", name="ApiVG2", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 22), value=90.0))
    await db_session.commit()

    # Skalar tesis değişkeni (version=3) — window + grain birlikte gerekli
    var = FacilityVariable(
        code="var_api2",
        name="Api Var 2",
        kind="scalar",
        unit="m3",
        version=3,
        default_time_grain="day",
        expression_json=json.dumps(
            {
                "op": "reduce",
                "reduce": "sum",
                "source": {
                    "op": "series",
                    "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta",
                    "grain": "day",
                    "window": "day",
                },
            }
        ),
    )
    db_session.add(var)
    await db_session.commit()
    await db_session.refresh(var)

    # Şablon API üzerinden oluştur
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    create_resp = await client.post(
        "/api/advanced-reports/templates",
        json={
            "name": "ApiVarTmpl2",
            "tag_ids": [],
            "variable_ids": [var.id],
            "output_format": "json",
            "time_range_type": "custom",
            "custom_start": "2026-06-01T00:00:00",
            "custom_end": "2026-06-02T00:00:00",
            "interval": "daily",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    tid = create_resp.json()["id"]

    # Gerçek ORM şablonunu çek
    tmpl = await db_session.get(ReportTemplate, tid)

    # Arşiv kaydı oluştur (pending)
    archive = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=start,
        end=end,
        interval="daily",
        output_format="json",
        template_id=tid,
    )
    db_session.add(archive)
    await db_session.commit()
    await db_session.refresh(archive)

    # BackgroundTask yolu ayrı AsyncSessionLocal açtığından test DB'sini görmez;
    # generate_report_from_template'i doğrudan aynı db_session üzerinden çalıştırıyoruz.
    await generate_report_from_template(tmpl, start, end, db_session, archive.id, lang="en")
    await db_session.refresh(archive)
    assert archive.status == "completed"

    # API GET /archive/{id} yanıtında variable_refs dolu olmalı
    got = await client.get(f"/api/advanced-reports/archive/{archive.id}", headers=headers)
    assert got.status_code == 200, got.text
    data = got.json()
    refs = data.get("variable_refs")
    assert refs is not None, f"variable_refs yanıtta eksik: {data}"
    assert len(refs) > 0, "variable_refs boş"
    assert refs[0]["variable_id"] == var.id
    assert refs[0]["version"] == 3
