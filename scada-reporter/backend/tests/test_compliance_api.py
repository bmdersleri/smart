"""Compliance API tests: RBAC, permit creation, evaluate, events, notes, status."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
)
from app.models.tag import Tag, TagReading
from app.models.user import User


async def _login(
    client: AsyncClient, db: AsyncSession, username: str, role: str = "operator"
) -> str:
    user = User(
        username=username,
        email=f"{username}@t.com",
        hashed_password=hash_password("pw123"),
        role=role,
    )
    db.add(user)
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


def _ts(year=2026, month=6, day=1, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute)


async def _seed_permit_with_breach(db: AsyncSession, *, requires_explanation: bool = False) -> int:
    permit = CompliancePermit(name="Permit API")
    point = ComplianceDischargePoint(permit=permit, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=API_COD", name="API_COD")
    parameter = ComplianceParameter(
        permit=permit,
        discharge_point=point,
        parameter_name="COD",
        source_type="scada",
        tag=tag,
    )
    limit = ComplianceLimit(
        parameter=parameter,
        limit_type="value_limit",
        aggregation="instant",
        max_value=10.0,
        requires_explanation=requires_explanation,
    )
    db.add_all([permit, point, tag, parameter, limit])
    await db.flush()
    db.add(TagReading(tag_id=tag.id, value=12.0, quality=192, timestamp=_ts(2026, 6, 1, 12)))
    await db.commit()
    return permit.id


@pytest.mark.asyncio
async def test_admin_can_create_permit(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cmp_admin", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/permits",
        json={"name": "May Permit", "report_frequency": "monthly"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "May Permit"
    assert body["report_frequency"] == "monthly"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_operator_cannot_create_permit(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cmp_op", role="operator")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/permits",
        json={"name": "Nope", "report_frequency": "monthly"},
        headers=h,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_custom_cron_without_cron_rejected(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cmp_cron", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/permits",
        json={"name": "Cron", "report_frequency": "custom_cron"},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_frequency_rejected(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "cmp_freq", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/permits",
        json={"name": "Bad", "report_frequency": "hourly"},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_operator_can_evaluate_and_list_events(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit_with_breach(db_session)
    tok = await _login(client, db_session, "cmp_eval", role="operator")
    h = {"Authorization": f"Bearer {tok}"}

    r = await client.post(
        "/api/compliance/evaluate",
        json={
            "permit_id": permit_id,
            "start": _ts(2026, 6, 1).isoformat(),
            "end": _ts(2026, 6, 2).isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1

    r2 = await client.get("/api/compliance/events", headers=h)
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] >= 1
    assert any(e["event_type"] == "limit_exceeded" for e in body["items"])


@pytest.mark.asyncio
async def test_overview_authenticated(client: AsyncClient, db_session: AsyncSession):
    await _seed_permit_with_breach(db_session)
    tok = await _login(client, db_session, "cmp_over", role="viewer")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.get("/api/compliance/overview", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "active_permits" in body
    assert "open_events" in body
    assert "packs_waiting" in body


@pytest.mark.asyncio
async def test_first_note_resolves_needs_explanation(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit_with_breach(db_session, requires_explanation=True)
    tok = await _login(client, db_session, "cmp_note", role="operator")
    h = {"Authorization": f"Bearer {tok}"}

    await client.post(
        "/api/compliance/evaluate",
        json={
            "permit_id": permit_id,
            "start": _ts(2026, 6, 1).isoformat(),
            "end": _ts(2026, 6, 2).isoformat(),
        },
        headers=h,
    )

    events = (await client.get("/api/compliance/events", headers=h)).json()["items"]
    source = next(e for e in events if e["event_type"] == "limit_exceeded")
    needs = next(e for e in events if e["event_type"] == "needs_explanation")
    assert needs["status"] == "open"

    r = await client.post(
        f"/api/compliance/events/{source['id']}/notes",
        json={"note": "Operator explanation."},
        headers=h,
    )
    assert r.status_code == 201, r.text

    refreshed = (await client.get(f"/api/compliance/events/{needs['id']}", headers=h)).json()
    assert refreshed["status"] == "resolved"


@pytest.mark.asyncio
async def test_waive_without_reason_rejected(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit_with_breach(db_session)
    tok = await _login(client, db_session, "cmp_waive", role="operator")
    h = {"Authorization": f"Bearer {tok}"}
    await client.post(
        "/api/compliance/evaluate",
        json={
            "permit_id": permit_id,
            "start": _ts(2026, 6, 1).isoformat(),
            "end": _ts(2026, 6, 2).isoformat(),
        },
        headers=h,
    )
    events = (await client.get("/api/compliance/events", headers=h)).json()["items"]
    eid = events[0]["id"]

    r = await client.patch(
        f"/api/compliance/events/{eid}/status",
        json={"status": "waived"},
        headers=h,
    )
    assert r.status_code == 422

    r2 = await client.patch(
        f"/api/compliance/events/{eid}/status",
        json={"status": "waived", "waive_reason": "Documented exception."},
        headers=h,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "waived"
