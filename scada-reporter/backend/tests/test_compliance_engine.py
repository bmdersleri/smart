import json
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.lab import LabParameter, LabSamplePoint
from app.models.tag import Tag, TagReading
from app.models.user import User
from app.services.compliance_engine import (
    ComplianceDischargePoint,
    ComplianceEvent,
    ComplianceEventNote,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
    build_event_key,
    evaluate_permit,
)


def _ts(year: int = 2026, month: int = 6, day: int = 1, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute)


async def _seed_scada_value_limit(db_session, *, requires_explanation: bool = False):
    permit = CompliancePermit(name="Permit A")
    point = ComplianceDischargePoint(permit=permit, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=COD", name="COD")
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
    db_session.add_all([permit, point, tag, parameter, limit])
    await db_session.flush()
    db_session.add(
        TagReading(tag_id=tag.id, value=12.0, quality=192, timestamp=_ts(2026, 6, 1, 12))
    )
    await db_session.flush()
    return permit, parameter, limit


async def _seed_hybrid_without_lab(db_session):
    permit = CompliancePermit(name="Permit B")
    sample_point = LabSamplePoint(code="LP1", name="Lab Point 1")
    point = ComplianceDischargePoint(
        permit=permit,
        code="OUT",
        name="Outfall",
        lab_sample_point=sample_point,
    )
    tag = Tag(node_id="ns=1;s=NH3", name="NH3")
    lab_parameter = LabParameter(code="NH3", name="Ammonia")
    parameter = ComplianceParameter(
        permit=permit,
        discharge_point=point,
        parameter_name="NH3",
        source_type="hybrid",
        tag=tag,
        lab_parameter=lab_parameter,
    )
    limit = ComplianceLimit(
        parameter=parameter,
        limit_type="sample_count",
        aggregation="count",
        max_value=1.0,
    )
    db_session.add_all([permit, sample_point, point, tag, lab_parameter, parameter, limit])
    await db_session.flush()
    db_session.add(TagReading(tag_id=tag.id, value=2.5, quality=192, timestamp=_ts(2026, 6, 1, 10)))
    await db_session.flush()
    return permit, parameter, limit


async def _seed_bad_quality(db_session, *, limit_max_value: float = 0.0):
    permit = CompliancePermit(name="Permit C")
    point = ComplianceDischargePoint(permit=permit, code="OUT", name="Outfall")
    tag = Tag(node_id="ns=1;s=TSS", name="TSS")
    parameter = ComplianceParameter(
        permit=permit,
        discharge_point=point,
        parameter_name="TSS",
        source_type="scada",
        tag=tag,
    )
    limit = ComplianceLimit(
        parameter=parameter,
        limit_type="quality",
        aggregation="instant",
        max_value=limit_max_value,
    )
    db_session.add_all([permit, point, tag, parameter, limit])
    await db_session.flush()
    db_session.add(TagReading(tag_id=tag.id, value=7.0, quality=0, timestamp=_ts(2026, 6, 1, 14)))
    await db_session.flush()
    return permit, parameter, limit


@pytest.mark.asyncio
async def test_evaluate_upserts_limit_event(db_session):
    permit, parameter, limit = await _seed_scada_value_limit(db_session)
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    first = await evaluate_permit(db_session, permit.id, start, end)
    second = await evaluate_permit(db_session, permit.id, start, end)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert build_event_key(permit.id, parameter.id, limit.id, "limit_exceeded", start, end)

    events = (await db_session.execute(select(ComplianceEvent))).scalars().all()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "limit_exceeded"
    assert event.observed_value == 12.0
    assert event.limit_value == 10.0


@pytest.mark.asyncio
async def test_hybrid_missing_lab_keeps_missing_sample_open(db_session):
    permit, _, _ = await _seed_hybrid_without_lab(db_session)
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    result = await evaluate_permit(db_session, permit.id, start, end)

    assert result["created"] >= 1
    event = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(ComplianceEvent.permit_id == permit.id)
            )
        )
        .scalars()
        .first()
    )
    assert event is not None
    assert event.event_type == "missing_sample"
    assert event.status == "open"
    assert "provisional_scada" in json.loads(event.evidence_json)


@pytest.mark.asyncio
async def test_bad_quality_creates_event(db_session):
    permit, _, _ = await _seed_bad_quality(db_session, limit_max_value=0.0)
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    result = await evaluate_permit(db_session, permit.id, start, end)

    assert result["created"] == 1
    event = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(ComplianceEvent.permit_id == permit.id)
            )
        )
        .scalars()
        .first()
    )
    assert event is not None
    assert event.event_type == "bad_quality"
    assert event.status == "open"


@pytest.mark.asyncio
async def test_bad_quality_threshold_is_fixed_at_opc_good(db_session):
    permit, _, _ = await _seed_bad_quality(db_session, limit_max_value=0.0)
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    result = await evaluate_permit(db_session, permit.id, start, end)

    assert result["created"] == 1
    event = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(ComplianceEvent.permit_id == permit.id)
            )
        )
        .scalars()
        .one()
    )
    assert event.event_type == "bad_quality"
    assert event.observed_value == 0


@pytest.mark.asyncio
async def test_resolved_source_event_gets_resolved_at(db_session):
    permit, _, _ = await _seed_scada_value_limit(db_session)
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    await evaluate_permit(db_session, permit.id, start, end)
    reading = (
        (await db_session.execute(select(TagReading).join(Tag).where(Tag.node_id == "ns=1;s=COD")))
        .scalars()
        .one()
    )
    reading.value = 8.0
    await db_session.flush()

    await evaluate_permit(db_session, permit.id, start, end)
    event = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(
                    ComplianceEvent.permit_id == permit.id,
                    ComplianceEvent.event_type == "limit_exceeded",
                )
            )
        )
        .scalars()
        .one()
    )

    assert event.status == "resolved"
    assert event.resolved_at is not None


@pytest.mark.asyncio
async def test_needs_explanation_resolves_when_note_exists(db_session):
    permit, _, _ = await _seed_scada_value_limit(db_session, requires_explanation=True)
    user = User(username="operator", email="operator@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    start = _ts(2026, 6, 1)
    end = _ts(2026, 6, 2)

    await evaluate_permit(db_session, permit.id, start, end)
    source_event = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(
                    ComplianceEvent.permit_id == permit.id,
                    ComplianceEvent.event_type == "limit_exceeded",
                )
            )
        )
        .scalars()
        .one()
    )

    db_session.add(ComplianceEventNote(event_id=source_event.id, user_id=user.id, note="Explained"))
    await db_session.flush()

    await evaluate_permit(db_session, permit.id, start, end)
    needs_explanation = (
        (
            await db_session.execute(
                select(ComplianceEvent).where(
                    ComplianceEvent.permit_id == permit.id,
                    ComplianceEvent.event_type == "needs_explanation",
                )
            )
        )
        .scalars()
        .one()
    )

    assert needs_explanation.status == "resolved"
    assert needs_explanation.resolved_at is not None
