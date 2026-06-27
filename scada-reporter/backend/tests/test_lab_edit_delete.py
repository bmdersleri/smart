from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.audit_log import AuditLog
from app.models.lab import LabParameter, LabSamplePoint


def _as(role: str, uid: int):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def _seed(db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH")
    db_session.add_all([point, param])
    await db_session.commit()
    await db_session.refresh(point)
    await db_session.refresh(param)
    return point, param


async def _make_sample(client, point_id, param_id):
    return (
        await client.post(
            "/api/lab/samples",
            json={
                "sample_point_id": point_id,
                "sampled_at": "2026-06-27T09:00:00",
                "measurements": [{"parameter_id": param_id, "value": 7.0}],
            },
        )
    ).json()


@pytest.mark.asyncio
async def test_owner_can_delete_own_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 204
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "lab.sample.delete")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_operator_cannot_delete_others_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    _as("operator", uid=99)  # different operator
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_any_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    _as("admin", uid=1)
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 204
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "lab.sample.delete")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_owner_can_edit_and_audit_written(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    resp = await client.patch(
        f"/api/lab/samples/{s['id']}",
        json={
            "sample_point_id": point.id,
            "sampled_at": "2026-06-27T09:00:00",
            "measurements": [{"parameter_id": param.id, "value": 8.5}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["measurements"][0]["value"] == 8.5
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "lab.sample.update")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_filters_by_point(client, db_session):
    point, param = await _seed(db_session)
    other = LabSamplePoint(code="OUT", name="Out")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    _as("operator", uid=7)
    await _make_sample(client, point.id, param.id)
    await _make_sample(client, other.id, param.id)
    resp = await client.get(f"/api/lab/samples?point_id={point.id}")
    assert resp.status_code == 200
    assert all(s["sample_point_id"] == point.id for s in resp.json())
    assert len(resp.json()) == 1
