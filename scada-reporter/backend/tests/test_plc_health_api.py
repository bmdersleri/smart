# tests/test_plc_health_api.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
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
async def test_health_endpoint_returns_rows(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "h_admin")
    db_session.add(PlcHealth(plc_ip="10.0.0.1", plc_name="P1", connected=True))
    await db_session.commit()
    r = await client.get("/api/plc/health", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()[0]["plc_ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_incidents_open_filter_and_summary(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "i_admin")
    from datetime import UTC, datetime

    db_session.add(
        PlcIncident(
            plc_ip="10.0.0.1",
            plc_name="P1",
            kind="disconnected",
            severity="critical",
            message="down",
        )
    )
    db_session.add(
        PlcIncident(
            plc_ip="10.0.0.2",
            plc_name="P2",
            kind="flapping",
            severity="warning",
            message="flap",
            resolved_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    h = {"Authorization": f"Bearer {tok}"}

    r_open = await client.get("/api/plc/incidents?open=true", headers=h)
    assert r_open.status_code == 200
    assert len(r_open.json()) == 1
    assert r_open.json()[0]["kind"] == "disconnected"

    r_sum = await client.get("/api/plc/incidents/summary", headers=h)
    assert r_sum.json() == {"open_total": 1, "critical": 1, "warning": 0}


@pytest.mark.asyncio
async def test_ack_incident(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "a_admin")
    inc = PlcIncident(
        plc_ip="10.0.0.1", plc_name="P1", kind="disconnected", severity="critical", message="down"
    )
    db_session.add(inc)
    await db_session.commit()
    await db_session.refresh(inc)
    r = await client.post(
        f"/api/plc/incidents/{inc.id}/ack", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
    await db_session.refresh(inc)
    assert inc.acknowledged_by == "a_admin"
    assert inc.acknowledged_at is not None


@pytest.mark.asyncio
async def test_ack_incident_404(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "ack404_admin")
    r = await client.post(
        "/api/plc/incidents/99999/ack",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404
