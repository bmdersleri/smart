from datetime import datetime

import pytest

from app.services.facility_variables.resolver import evaluate_variable
from app.services.facility_variables.service import create_variable


async def _make(db, code, expression, kind="scalar"):
    return await create_variable(
        db,
        code=code,
        name=code,
        description="",
        kind=kind,
        unit="",
        expression=expression,
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )


JUNE = (datetime(2026, 6, 1), datetime(2026, 7, 1))


@pytest.mark.asyncio
async def test_evaluate_const_variable(db_session):
    var = await _make(db_session, "c", {"op": "const", "value": 7.0})
    res = await evaluate_variable(
        db_session, var, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.kind == "scalar"
    assert res.scalar == 7.0


@pytest.mark.asyncio
async def test_ref_resolves_active_variable(db_session):
    a = await _make(db_session, "a", {"op": "const", "value": 5.0})
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    res = await evaluate_variable(
        db_session, b, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.scalar == 5.0


@pytest.mark.asyncio
async def test_ref_to_inactive_yields_none(db_session):
    from app.services.facility_variables.service import deactivate_variable

    a = await _make(db_session, "a", {"op": "const", "value": 5.0})
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    await deactivate_variable(db_session, a.id)
    res = await evaluate_variable(
        db_session, b, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.scalar is None
