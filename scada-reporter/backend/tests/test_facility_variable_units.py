import pytest

from app.models.tag import Tag
from app.services.facility_variables.units import unit_warnings


async def _tag(db, name, unit):
    t = Tag(node_id=name, name=name, unit=unit)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_add_incompatible_units_warns(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    b = await _tag(db_session, "B", "kWh/gun")
    expr = {
        "op": "add",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "agg", "source": {"type": "tag", "tag_id": b.id}, "agg": "sum", "window": "day"},
        ],
    }
    warns = await unit_warnings(db_session, expr)
    assert warns


@pytest.mark.asyncio
async def test_add_same_units_no_warn(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    b = await _tag(db_session, "B", "m3/gun")
    expr = {
        "op": "add",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "agg", "source": {"type": "tag", "tag_id": b.id}, "agg": "sum", "window": "day"},
        ],
    }
    assert await unit_warnings(db_session, expr) == []


@pytest.mark.asyncio
async def test_mul_never_warns(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    expr = {
        "op": "mul",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "const", "value": 3.0},
        ],
    }
    assert await unit_warnings(db_session, expr) == []
