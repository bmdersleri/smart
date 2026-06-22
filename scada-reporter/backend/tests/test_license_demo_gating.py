"""Integration: DEMO mode is read-only, gates premium features, caps tag list."""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import LicenseInfo, set_active_license, set_demo_mode
from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User


@pytest.fixture(autouse=True)
def _reset_state():
    set_active_license(None)
    yield
    set_active_license(None)


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


def _full_license() -> LicenseInfo:
    return LicenseInfo(
        license_id="lic",
        customer="ACME",
        product="ekont-smart-report",
        features=("advanced_reports", "grafana", "realtime", "export"),
        max_tags=None,
        expires_at=None,
    )


# ── demo read-only ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_blocks_tag_create(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_create")
    h = {"Authorization": f"Bearer {tok}"}
    set_demo_mode()
    r = await client.post("/api/tags/", json={"name": "X", "plc_name": "P"}, headers=h)
    assert r.status_code == 403
    assert "demo" in r.text.lower()


@pytest.mark.asyncio
async def test_demo_blocks_import_csv(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_imp")
    h = {"Authorization": f"Bearer {tok}"}
    set_demo_mode()
    files = {"file": ("t.csv", io.BytesIO(b"name\nFoo\n"), "text/csv")}
    r = await client.post("/api/tags/import_csv", files=files, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_demo_blocks_tag_delete(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_del")
    h = {"Authorization": f"Bearer {tok}"}
    db_session.add(Tag(node_id="D:1", name="T", plc_name="P"))
    await db_session.commit()
    tag_id = (await client.get("/api/tags/", headers=h)).json()[0]["id"]
    set_demo_mode()
    r = await client.delete(f"/api/tags/{tag_id}", headers=h)
    assert r.status_code == 403


# ── demo gates premium features ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_blocks_export(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_exp")
    h = {"Authorization": f"Bearer {tok}"}
    set_demo_mode()
    r = await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_demo_blocks_advanced_reports(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_adv")
    h = {"Authorization": f"Bearer {tok}"}
    set_demo_mode()
    r = await client.get("/api/advanced-reports/templates", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_demo_blocks_realtime(client: AsyncClient, db_session: AsyncSession):
    set_demo_mode()
    r = await client.get("/api/dashboard/stream", params={"token": "dummy", "limit": 1})
    assert r.status_code == 403


# ── demo caps tag visibility ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_caps_tag_list(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "d_list")
    h = {"Authorization": f"Bearer {tok}"}
    for i in range(30):
        db_session.add(Tag(node_id=f"L:{i}", name=f"T{i}", plc_name="P"))
    await db_session.commit()
    set_demo_mode(demo_max_tags=5)
    tags = (await client.get("/api/tags/", headers=h)).json()
    assert len(tags) == 5


# ── licensed contrast ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_licensed_allows_export_and_write(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "lic_ok")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_full_license())
    assert (
        await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    ).status_code == 200
    r = await client.post("/api/tags/", json={"name": "Y", "plc_name": "P"}, headers=h)
    assert r.status_code != 403
