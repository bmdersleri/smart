"""Tag import/export tests: CSV + XLSX export, generic CSV import."""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User


async def _admin(client: AsyncClient, db: AsyncSession, username: str) -> str:
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
async def test_export_csv_contains_tag(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "exp_csv")
    h = {"Authorization": f"Bearer {tok}"}
    db_session.add(
        Tag(node_id="EXP,DD0", name="ExpTag", plc_name="PLC9", unit="bar", long_term=True)
    )
    await db_session.commit()

    r = await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.text
    assert "name" in body  # header row
    assert "ExpTag" in body
    assert "PLC9" in body


@pytest.mark.asyncio
async def test_export_xlsx_returns_spreadsheet(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "exp_xlsx")
    h = {"Authorization": f"Bearer {tok}"}
    db_session.add(Tag(node_id="EXP2,DD0", name="ExpTag2", long_term=True))
    await db_session.commit()

    r = await client.get("/api/tags/export", params={"format": "xlsx"}, headers=h)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 100


@pytest.mark.asyncio
async def test_import_csv_creates_tags(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "imp_csv")
    h = {"Authorization": f"Bearer {tok}"}
    # WinCC adresleri virgül içerir -> CSV'de tırnaklanır (export aynısını yapar)
    csv = (
        "name,plc_name,plc_ip,s7_address,data_type,unit,sample_interval\n"
        'Debi1,PLC1,192.168.1.5,"DB1,DD0",float32,m3h,5\n'
        'Seviye1,PLC1,192.168.1.5,"DB1,DD4",float32,m,10\n'
    )
    files = {"file": ("tags.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = await client.post("/api/tags/import_csv", files=files, headers=h)
    assert r.status_code == 200
    assert r.json()["imported"] == 2

    tags = (await client.get("/api/tags/", headers=h)).json()
    names = {t["name"] for t in tags}
    assert {"Debi1", "Seviye1"} <= names


@pytest.mark.asyncio
async def test_import_csv_skips_duplicates(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "imp_dup")
    h = {"Authorization": f"Bearer {tok}"}
    csv = "node_id,name,plc_name\nDUP:1,DupTag,PLCX\n"
    files = {"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")}
    r1 = await client.post("/api/tags/import_csv", files=files, headers=h)
    assert r1.json()["imported"] == 1

    files2 = {"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")}
    r2 = await client.post("/api/tags/import_csv", files=files2, headers=h)
    assert r2.json()["imported"] == 0
    assert r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_import_csv_requires_role(client: AsyncClient, db_session: AsyncSession):
    db_session.add(
        User(
            username="imp_viewer",
            email="imp_viewer@t.com",
            hashed_password=hash_password("pw123"),
            role="viewer",
        )
    )
    await db_session.commit()
    tok = (
        await client.post("/api/auth/token", data={"username": "imp_viewer", "password": "pw123"})
    ).json()["access_token"]
    files = {"file": ("t.csv", io.BytesIO(b"name\nX\n"), "text/csv")}
    r = await client.post(
        "/api/tags/import_csv", files=files, headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 403
