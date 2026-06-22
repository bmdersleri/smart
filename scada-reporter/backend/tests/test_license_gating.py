"""Integration: license feature gating + tag quota enforced at the HTTP layer.

Active license is set via ``set_active_license`` (normally done at startup from
the verified token) and reset after each test so other suites stay unrestricted.
"""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import LicenseInfo, set_active_license
from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User


def _license(*, features=(), max_tags=None) -> LicenseInfo:
    return LicenseInfo(
        license_id="lic",
        customer="Cust",
        product="ekont-smart-report",
        features=tuple(features),
        max_tags=max_tags,
        expires_at=None,
    )


@pytest.fixture(autouse=True)
def _reset_active_license():
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


def _csv_files(rows: int):
    lines = "".join(f"QTag{i},PLCQ\n" for i in range(rows))
    csv = "name,plc_name\n" + lines
    return {"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")}


# ── tag quota ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_tag_blocked_when_quota_exceeded(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _admin_token(client, db_session, "q_block")
    h = {"Authorization": f"Bearer {tok}"}
    db_session.add(Tag(node_id="Q:1", name="Existing", plc_name="PLCQ"))
    await db_session.commit()
    set_active_license(_license(max_tags=1))

    r = await client.post("/api/tags/", json={"name": "New", "plc_name": "PLCQ"}, headers=h)
    assert r.status_code == 403
    assert "limit" in r.text.lower()


@pytest.mark.asyncio
async def test_import_csv_blocked_when_quota_exceeded(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _admin_token(client, db_session, "q_bulk")
    h = {"Authorization": f"Bearer {tok}"}
    db_session.add(Tag(node_id="Q:exist", name="Existing", plc_name="PLCQ"))
    await db_session.commit()
    set_active_license(_license(max_tags=3))  # 1 existing + 3 new = 4 > 3

    r = await client.post("/api/tags/import_csv", files=_csv_files(3), headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_import_csv_allowed_within_quota(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "q_ok")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_license(max_tags=5))

    r = await client.post("/api/tags/import_csv", files=_csv_files(3), headers=h)
    assert r.status_code == 200
    assert r.json()["imported"] == 3


# ── feature gating ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_blocked_without_feature(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "f_exp_no")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_license(features=["reports"]))

    r = await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_export_allowed_with_feature(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "f_exp_yes")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_license(features=["export"]))

    r = await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_export_allowed_when_unlicensed(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "f_exp_none")
    h = {"Authorization": f"Bearer {tok}"}
    # No active license -> full version.
    r = await client.get("/api/tags/export", params={"format": "csv"}, headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_advanced_reports_blocked_without_feature(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _admin_token(client, db_session, "f_adv")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_license(features=["reports"]))

    r = await client.get("/api/advanced-reports/templates", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_grafana_sync_blocked_without_feature(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "f_graf")
    h = {"Authorization": f"Bearer {tok}"}
    set_active_license(_license(features=["reports"]))

    r = await client.post("/api/dashboard/watchlist-groups/sync-grafana", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_realtime_stream_blocked_without_feature(
    client: AsyncClient, db_session: AsyncSession
):
    set_active_license(_license(features=["reports"]))
    # Feature gate runs as a dependency, before the in-body token check, so a
    # dummy token still yields 403 (not 401) when the feature is missing.
    r = await client.get("/api/dashboard/stream", params={"token": "dummy", "limit": 1})
    assert r.status_code == 403
