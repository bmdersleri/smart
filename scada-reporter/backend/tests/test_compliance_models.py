from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceEvent,
    ComplianceEventNote,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
)
from app.models.user import User


def test_compliance_table_names_are_stable():
    assert CompliancePermit.__tablename__ == "compliance_permits"
    assert ComplianceLimit.__tablename__ == "compliance_limits"
    assert ComplianceEvent.__tablename__ == "compliance_events"


def test_event_key_is_unique_constraint():
    names = {constraint.name for constraint in ComplianceEvent.__table__.constraints}
    assert "uq_compliance_events_event_key" in names


async def _enable_foreign_keys(db_session):
    await db_session.execute(text("PRAGMA foreign_keys=ON"))


async def _persist_graph(db_session):
    user = User(username="operator", email="operator@example.com", hashed_password="x")
    permit = CompliancePermit(name="Permit A")
    db_session.add_all([user, permit])
    await db_session.flush()

    point = ComplianceDischargePoint(
        permit_id=permit.id,
        code="OUT",
        name="Outfall",
    )
    db_session.add(point)
    await db_session.flush()

    parameter = ComplianceParameter(
        permit_id=permit.id,
        discharge_point_id=point.id,
        parameter_name="COD",
        source_type="scada",
    )
    db_session.add(parameter)
    await db_session.flush()

    limit = ComplianceLimit(
        compliance_parameter_id=parameter.id,
        limit_type="value_limit",
        max_value=10.0,
    )
    db_session.add(limit)
    await db_session.flush()

    event = ComplianceEvent(
        permit_id=permit.id,
        parameter_id=parameter.id,
        limit_id=limit.id,
        event_type="limit_exceeded",
        period_start=datetime(2026, 6, 1),
        period_end=datetime(2026, 6, 2),
        event_key=f"event-{permit.id}-{parameter.id}-{limit.id}",
    )
    db_session.add(event)
    await db_session.flush()

    note = ComplianceEventNote(event_id=event.id, user_id=user.id, note="Explained")
    db_session.add(note)
    await db_session.commit()
    return permit, point, parameter, limit, event, note


@pytest.mark.asyncio
async def test_full_compliance_graph_persists(db_session):
    await _enable_foreign_keys(db_session)

    _, _, _, _, event, note = await _persist_graph(db_session)

    rows = (await db_session.execute(select(ComplianceEventNote))).scalars().all()
    assert rows == [note]
    assert rows[0].event_id == event.id


@pytest.mark.asyncio
async def test_parameter_permit_must_match_discharge_point_permit(db_session):
    await _enable_foreign_keys(db_session)
    permit_a = CompliancePermit(name="Permit A")
    permit_b = CompliancePermit(name="Permit B")
    db_session.add_all([permit_a, permit_b])
    await db_session.flush()

    point = ComplianceDischargePoint(permit_id=permit_a.id, code="A", name="Outfall A")
    db_session.add(point)
    await db_session.flush()

    db_session.add(
        ComplianceParameter(
            permit_id=permit_b.id,
            discharge_point_id=point.id,
            parameter_name="COD",
            source_type="scada",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_event_permit_must_match_parameter_permit(db_session):
    await _enable_foreign_keys(db_session)
    permit, _, parameter, limit, _, _ = await _persist_graph(db_session)
    permit_b = CompliancePermit(name="Permit B")
    db_session.add(permit_b)
    await db_session.flush()

    db_session.add(
        ComplianceEvent(
            permit_id=permit_b.id,
            parameter_id=parameter.id,
            limit_id=limit.id,
            event_type="limit_exceeded",
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 2),
            event_key=f"wrong-permit-{permit.id}",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_event_limit_must_match_parameter(db_session):
    await _enable_foreign_keys(db_session)
    permit, point, parameter, _, _, _ = await _persist_graph(db_session)

    other_parameter = ComplianceParameter(
        permit_id=permit.id,
        discharge_point_id=point.id,
        parameter_name="TSS",
        source_type="scada",
    )
    db_session.add(other_parameter)
    await db_session.flush()
    other_limit = ComplianceLimit(
        compliance_parameter_id=other_parameter.id,
        limit_type="value_limit",
        max_value=5.0,
    )
    db_session.add(other_limit)
    await db_session.flush()

    db_session.add(
        ComplianceEvent(
            permit_id=permit.id,
            parameter_id=parameter.id,
            limit_id=other_limit.id,
            event_type="limit_exceeded",
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 2),
            event_key=f"wrong-limit-{permit.id}",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_deleting_permit_with_children_is_restricted(db_session):
    await _enable_foreign_keys(db_session)
    permit, _, _, _, _, _ = await _persist_graph(db_session)

    await db_session.delete(permit)

    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.commit()
