import json

import pytest

from app.services.facility_variables.service import (
    VariableError,
    create_variable,
    update_variable,
)


def _scalar_const(value=1.0):
    return {"op": "const", "value": value}


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


@pytest.mark.asyncio
async def test_create_stores_dependencies(db_session):
    expr = {
        "op": "agg",
        "source": {"type": "tag", "tag_id": 5},
        "agg": "delta",
        "window": "day",
    }
    var = await _make(db_session, "v1", expr)
    assert var.version == 1
    assert len(var.dependencies) == 1
    dep = var.dependencies[0]
    assert dep.depends_on_type == "tag"
    assert dep.depends_on_tag_id == 5


@pytest.mark.asyncio
async def test_create_rejects_invalid_expression(db_session):
    with pytest.raises(VariableError):
        await _make(db_session, "bad", {"op": "div", "args": [_scalar_const(), _scalar_const()]})


@pytest.mark.asyncio
async def test_update_bumps_version_on_expression_change(db_session):
    var = await _make(db_session, "v2", _scalar_const(1.0))
    updated = await update_variable(
        db_session,
        var.id,
        name="v2",
        description="",
        unit="",
        expression=_scalar_const(2.0),
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        updated_by=1,
    )
    assert updated.version == 2
    assert json.loads(updated.expression_json)["value"] == 2.0


@pytest.mark.asyncio
async def test_update_no_bump_on_cosmetic_change(db_session):
    var = await _make(db_session, "v3", _scalar_const(1.0))
    updated = await update_variable(
        db_session,
        var.id,
        name="renamed",
        description="desc",
        unit="",
        expression=_scalar_const(1.0),
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        updated_by=1,
    )
    assert updated.version == 1
    assert updated.name == "renamed"


@pytest.mark.asyncio
async def test_create_rejects_direct_cycle(db_session):
    a = await _make(db_session, "a", _scalar_const(1.0))
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    # now make a reference b → cycle a→b→a
    with pytest.raises(VariableError, match="döngü|cycle"):
        await update_variable(
            db_session,
            a.id,
            name="a",
            description="",
            unit="",
            expression={"op": "ref", "variable_id": b.id},
            null_policy="skip",
            quality_policy="good_only",
            default_time_grain="day",
            updated_by=1,
        )
