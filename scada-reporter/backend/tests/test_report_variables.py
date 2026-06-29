"""resolve_report_variables: evaluate selected variables over the report window."""

import json
from datetime import datetime

import pytest

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag, TagReading
from app.services.report_variables import resolve_report_variables


async def _seed_tag(db, name="P", unit="m3"):
    tag = Tag(node_id=f"ns=2;s={name}", name=name, unit=unit)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


async def _add_var(db, *, code, kind, expr, unit="m3", grain="day", active=True, version=1):
    var = FacilityVariable(
        code=code,
        name=code,
        kind=kind,
        unit=unit,
        expression_json=json.dumps(expr),
        default_time_grain=grain,
        is_active=active,
        version=version,
    )
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


@pytest.mark.asyncio
async def test_scalar_variable_resolves_value_and_ref(db_session):
    tag = await _seed_tag(db_session)
    # two readings same day -> delta = last - first = 40
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 20), value=50.0))
    await db_session.commit()
    var = await _add_var(
        db_session,
        code="var_daily",
        kind="scalar",
        version=4,
        expr={
            "op": "reduce",
            "reduce": "sum",
            "source": {
                "op": "series",
                "source": {"type": "tag", "tag_id": tag.id},
                "agg": "delta",
                "grain": "day",
                "window": "day",
            },
        },
    )
    per_var, refs = await resolve_report_variables(
        db_session,
        [var.id],
        start=datetime(2026, 6, 1),
        end=datetime(2026, 6, 2),
        tz_offset_hours=3,
    )
    assert len(per_var) == 1
    item = per_var[0]
    assert item["kind"] == "scalar"
    assert item["code"] == "var_daily"
    assert item["value"] == pytest.approx(40.0)
    assert item["points"] is None
    assert item["warning"] is None
    assert refs[0] == {
        "variable_id": var.id,
        "code": "var_daily",
        "version": 4,
        "window": {
            "start": "2026-06-01T00:00:00",
            "end": "2026-06-02T00:00:00",
            "grain": "day",
            "tz_offset_hours": 3,
        },
        "warning": None,
    }


@pytest.mark.asyncio
async def test_series_variable_resolves_points(db_session):
    tag = await _seed_tag(db_session)
    for d, v, h in [(1, 5.0, 6), (1, 15.0, 18), (2, 20.0, 6), (2, 50.0, 18)]:
        db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, d, h), value=v))
    await db_session.commit()
    var = await _add_var(
        db_session,
        code="var_series",
        kind="series",
        expr={
            "op": "series",
            "source": {"type": "tag", "tag_id": tag.id},
            "agg": "max",
            "grain": "day",
            "window": "day",
        },
    )
    per_var, _ = await resolve_report_variables(
        db_session,
        [var.id],
        start=datetime(2026, 6, 1),
        end=datetime(2026, 6, 3),
        tz_offset_hours=3,
    )
    item = per_var[0]
    assert item["kind"] == "series"
    assert item["value"] is None
    # points sorted by bucket, ts carries +03:00 offset
    assert [p["value"] for p in item["points"]] == [15.0, 50.0]
    assert item["points"][0]["ts"].endswith("+03:00")


@pytest.mark.asyncio
async def test_inactive_variable_warns_not_silent(db_session):
    var = await _add_var(
        db_session,
        code="var_off",
        kind="scalar",
        active=False,
        expr={"op": "const", "value": 1.0},
    )
    per_var, refs = await resolve_report_variables(
        db_session,
        [var.id],
        start=datetime(2026, 6, 1),
        end=datetime(2026, 6, 2),
        tz_offset_hours=3,
    )
    assert per_var[0]["warning"] is not None
    assert per_var[0]["value"] is None
    assert refs[0]["warning"] is not None


@pytest.mark.asyncio
async def test_missing_variable_id_warns(db_session):
    per_var, refs = await resolve_report_variables(
        db_session,
        [999999],
        start=datetime(2026, 6, 1),
        end=datetime(2026, 6, 2),
        tz_offset_hours=3,
    )
    assert per_var[0]["warning"] is not None
    assert refs[0]["variable_id"] == 999999
    assert refs[0]["warning"] is not None
