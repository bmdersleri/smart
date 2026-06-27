from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.lab import LabParameter, LabSamplePoint
from app.models.tag import Tag, TagReading


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def _seed_point(db_session, code="INLET"):
    p = LabSamplePoint(code=code, name=code)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _seed_param(db_session, code="PH", **kw):
    param = LabParameter(code=code, name=code, **kw)
    db_session.add(param)
    await db_session.commit()
    await db_session.refresh(param)
    return param


@pytest.mark.asyncio
async def test_create_multi_parameter_sample(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH", min_limit=6.5, max_limit=9.0)
    cod = await _seed_param(db_session, code="COD", max_limit=400.0)
    _as("operator", uid=7)
    resp = await client.post(
        "/api/lab/samples",
        json={
            "sample_point_id": point.id,
            "sampled_at": "2026-06-27T09:00:00",
            "measurements": [
                {"parameter_id": ph.id, "value": 7.2},
                {"parameter_id": cod.id, "value": 320.0},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entered_by"] == 7
    assert len(body["measurements"]) == 2
    flags = {m["parameter_id"]: m["flag"] for m in body["measurements"]}
    assert flags[ph.id] is None
    assert flags[cod.id] is None


@pytest.mark.asyncio
async def test_over_limit_sets_flag(client, db_session):
    point = await _seed_point(db_session)
    cod = await _seed_param(db_session, code="COD", max_limit=400.0)
    _as("operator", uid=7)
    resp = await client.post(
        "/api/lab/samples",
        json={
            "sample_point_id": point.id,
            "sampled_at": "2026-06-27T09:00:00",
            "measurements": [{"parameter_id": cod.id, "value": 999.0}],
        },
    )
    assert resp.json()["measurements"][0]["flag"] == "over_limit"


@pytest.mark.asyncio
async def test_mirror_writes_tag_reading(client, db_session):
    tag = Tag(node_id="lab:ph", name="Lab pH")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH", mirror_to_tag_id=tag.id)
    _as("operator", uid=7)
    await client.post(
        "/api/lab/samples",
        json={
            "sample_point_id": point.id,
            "sampled_at": "2026-06-27T09:00:00",
            "measurements": [{"parameter_id": ph.id, "value": 7.4}],
        },
    )
    rows = (
        (await db_session.execute(select(TagReading).where(TagReading.tag_id == tag.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].value == 7.4


@pytest.mark.asyncio
async def test_no_mirror_when_unset(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH")  # mirror_to_tag_id None
    _as("operator", uid=7)
    await client.post(
        "/api/lab/samples",
        json={
            "sample_point_id": point.id,
            "sampled_at": "2026-06-27T09:00:00",
            "measurements": [{"parameter_id": ph.id, "value": 7.4}],
        },
    )
    rows = (await db_session.execute(select(TagReading))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_batch_insert(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH")
    _as("operator", uid=7)
    resp = await client.post(
        "/api/lab/samples/batch",
        json={
            "rows": [
                {
                    "sample_point_id": point.id,
                    "sampled_at": "2026-06-27T09:00:00",
                    "measurements": [{"parameter_id": ph.id, "value": 7.1}],
                },
                {
                    "sample_point_id": point.id,
                    "sampled_at": "2026-06-27T12:00:00",
                    "measurements": [{"parameter_id": ph.id, "value": 7.3}],
                },
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["inserted"] == 2
