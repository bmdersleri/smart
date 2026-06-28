"""Report-pack API + scheduler: full flow, blocking, freeze, download, RBAC, audit."""

import json
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
    ComplianceReportPack,
)
from app.models.tag import Tag, TagReading
from app.models.user import User
from app.services.compliance_engine import evaluate_permit
from app.services.scheduler import closed_period_bounds, compliance_period_close_job


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


async def _seed_permit(db: AsyncSession, *, requires_explanation: bool = False) -> int:
    permit = CompliancePermit(name="Pack Permit", report_frequency="monthly")
    point = ComplianceDischargePoint(permit=permit, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=PACK_COD", name="PACK_COD")
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


PERIOD = {"start": "2026-06-01T00:00:00", "end": "2026-07-01T00:00:00"}


@pytest.mark.asyncio
async def test_full_happy_path(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_admin", role="admin")
    h = {"Authorization": f"Bearer {tok}"}

    # create
    r = await client.post(
        "/api/compliance/report-packs",
        json={"permit_id": permit_id, **PERIOD},
        headers=h,
    )
    assert r.status_code == 201, r.text
    pack_id = r.json()["id"]
    assert r.json()["status"] == "draft"
    assert r.json()["prepared_by"] is not None

    # generate
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["has_pdf"] and body["has_xlsx"] and body["has_json"]

    # submit-review
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/submit-review", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready_for_review"

    # approve
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["approved_by"] is not None


@pytest.mark.asyncio
async def test_submit_review_requires_outputs(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_admin2", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    # no generate -> 409
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/submit-review", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_approve_blocked_when_explanation_open(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session, requires_explanation=True)
    await evaluate_permit(db_session, permit_id, _ts(2026, 6, 1), _ts(2026, 7, 1))
    await db_session.commit()

    tok = await _login(client, db_session, "pk_admin3", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)

    # detail shows blocking issues
    r = await client.get(f"/api/compliance/report-packs/{pack_id}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["blocking_issues"]) >= 1

    # approve blocked
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_approve_freezes_snapshot(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    await evaluate_permit(db_session, permit_id, _ts(2026, 6, 1), _ts(2026, 7, 1))
    await db_session.commit()

    tok = await _login(client, db_session, "pk_admin4", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=h)
    assert r.status_code == 200, r.text

    pack = await db_session.get(ComplianceReportPack, pack_id)
    await db_session.refresh(pack)
    frozen = pack.events_snapshot_json
    assert frozen is not None
    snapshot = json.loads(frozen)
    assert len(snapshot) >= 1

    # Re-evaluate the same period -> approved pack snapshot unchanged.
    await evaluate_permit(db_session, permit_id, _ts(2026, 6, 1), _ts(2026, 7, 1))
    await db_session.commit()
    pack2 = await db_session.get(ComplianceReportPack, pack_id)
    await db_session.refresh(pack2)
    assert pack2.events_snapshot_json == frozen
    assert pack2.status == "approved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fmt,ctype",
    [
        ("pdf", "application/pdf"),
        ("excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("json", "application/json"),
    ],
)
async def test_download_each_format(
    client: AsyncClient, db_session: AsyncSession, fmt: str, ctype: str
):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, f"pk_dl_{fmt}", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)

    r = await client.get(
        f"/api/compliance/report-packs/{pack_id}/download", params={"format": fmt}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(ctype)
    assert len(r.content) > 0


@pytest.mark.asyncio
async def test_download_missing_blob_404(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_dl_404", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    # not generated yet
    r = await client.get(
        f"/api/compliance/report-packs/{pack_id}/download", params={"format": "pdf"}, headers=h
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_approved_409(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_del", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)
    await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=h)

    r = await client.request("DELETE", f"/api/compliance/report-packs/{pack_id}", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_delete_draft_ok(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_del2", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    r = await client.request("DELETE", f"/api/compliance/report-packs/{pack_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["deleted"] is True


@pytest.mark.asyncio
async def test_operator_cannot_approve(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    admin_tok = await _login(client, db_session, "pk_admin5", role="admin")
    ah = {"Authorization": f"Bearer {admin_tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=ah
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=ah)

    op_tok = await _login(client, db_session, "pk_op", role="operator")
    oh = {"Authorization": f"Bearer {op_tok}"}
    r = await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=oh)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_filters_by_permit(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_list", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    r = await client.get("/api/compliance/report-packs", params={"permit_id": permit_id}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(item["permit_id"] == permit_id for item in body["items"])


@pytest.mark.asyncio
async def test_audit_rows_written(client: AsyncClient, db_session: AsyncSession):
    permit_id = await _seed_permit(db_session)
    tok = await _login(client, db_session, "pk_audit", role="admin")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/compliance/report-packs", json={"permit_id": permit_id, **PERIOD}, headers=h
    )
    pack_id = r.json()["id"]
    await client.post(f"/api/compliance/report-packs/{pack_id}/generate", headers=h)
    await client.post(f"/api/compliance/report-packs/{pack_id}/approve", headers=h)

    actions = (
        (
            await db_session.execute(
                select(AuditLog.action).where(AuditLog.target_type == "compliance_report_pack")
            )
        )
        .scalars()
        .all()
    )
    assert "compliance.reportpack.create" in actions
    assert "compliance.reportpack.generate" in actions
    assert "compliance.reportpack.approve" in actions


# --- Scheduler period-close job -------------------------------------------


def test_closed_period_bounds_monthly():
    start, end = closed_period_bounds("monthly", datetime(2026, 7, 15))
    assert start == datetime(2026, 6, 1)
    assert end == datetime(2026, 7, 1)


def test_closed_period_bounds_custom_cron_none():
    assert closed_period_bounds("custom_cron", datetime(2026, 7, 15)) is None


@pytest.mark.asyncio
async def test_period_close_creates_draft_and_skips_existing(db_session: AsyncSession, monkeypatch):
    permit = CompliancePermit(name="Close Permit", report_frequency="monthly", is_active=True)
    db_session.add(permit)
    await db_session.commit()

    # Patch the job's session factory (imported inside the job from
    # app.core.database) to reuse the test in-memory session.
    import contextlib

    import app.core.database as core_db

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield db_session

    monkeypatch.setattr(core_db, "AsyncSessionLocal", _fake_session)

    now = datetime(2026, 7, 15)
    await compliance_period_close_job(now=now)

    packs = (
        (
            await db_session.execute(
                select(ComplianceReportPack).where(ComplianceReportPack.permit_id == permit.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(packs) == 1
    assert packs[0].status == "draft"
    assert packs[0].period_start == datetime(2026, 6, 1)

    # Mark approved, re-run -> no new pack created (skip already-present period).
    packs[0].status = "approved"
    await db_session.commit()
    await compliance_period_close_job(now=now)
    packs2 = (
        (
            await db_session.execute(
                select(ComplianceReportPack).where(ComplianceReportPack.permit_id == permit.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(packs2) == 1
