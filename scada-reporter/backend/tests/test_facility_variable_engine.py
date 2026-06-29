from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.engine import EvalResult, evaluate, excel_round


async def _seed_totalizer(db, name, rows):
    tag = Tag(node_id=name, name=name, unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    for ts, val in rows:
        db.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db.commit()
    return tag


async def _noref(_vid):  # no ref in these tests
    raise AssertionError("ref not expected")


JUNE = (datetime(2026, 6, 1), datetime(2026, 6, 3))  # 2-day window


@pytest.mark.asyncio
async def test_excel_round_half_away_from_zero():
    assert excel_round(2.5, 0) == 3.0
    assert excel_round(3.5, 0) == 4.0
    assert excel_round(-2.5, 0) == -3.0
    assert excel_round(1.2345, 2) == 1.23


@pytest.mark.asyncio
async def test_agg_scalar_delta(db_session):
    tag = await _seed_totalizer(
        db_session, "T", [(datetime(2026, 6, 1, 0), 10.0), (datetime(2026, 6, 2, 23), 90.0)]
    )
    node = {
        "op": "agg",
        "source": {"type": "tag", "tag_id": tag.id},
        "agg": "delta",
        "window": "2d",
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.kind == "scalar"
    assert res.scalar == 80.0


@pytest.mark.asyncio
async def test_add_two_tag_deltas(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)]
    )
    t2 = await _seed_totalizer(
        db_session, "T2", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 10.0)]
    )
    node = {
        "op": "add",
        "args": [
            {
                "op": "series",
                "source": {"type": "tag", "tag_id": t1.id},
                "agg": "delta",
                "grain": "day",
                "window": "2d",
            },
            {
                "op": "series",
                "source": {"type": "tag", "tag_id": t2.id},
                "agg": "delta",
                "grain": "day",
                "window": "2d",
            },
        ],
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.kind == "series"
    assert res.series[datetime(2026, 6, 1)] == 50.0


@pytest.mark.asyncio
async def test_series_plus_scalar_broadcast(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)]
    )
    node = {
        "op": "add",
        "args": [
            {
                "op": "series",
                "source": {"type": "tag", "tag_id": t1.id},
                "agg": "delta",
                "grain": "day",
                "window": "2d",
            },
            {"op": "const", "value": 100.0},
        ],
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.series[datetime(2026, 6, 1)] == 140.0


@pytest.mark.asyncio
async def test_div_on_zero_null(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0), (datetime(2026, 6, 1, 23), 5.0)]
    )  # delta 0
    node = {
        "op": "div",
        "args": [
            {"op": "const", "value": 10.0},
            {
                "op": "agg",
                "source": {"type": "tag", "tag_id": t1.id},
                "agg": "delta",
                "window": "2d",
            },
        ],
        "on_zero": "null",
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.scalar is None


@pytest.mark.asyncio
async def test_null_propagation_in_add(db_session):
    # tag with a single reading → delta is None; None + const → None
    t1 = await _seed_totalizer(db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0)])
    node = {
        "op": "add",
        "args": [
            {
                "op": "agg",
                "source": {"type": "tag", "tag_id": t1.id},
                "agg": "delta",
                "window": "2d",
            },
            {"op": "const", "value": 1.0},
        ],
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.scalar is None


@pytest.mark.asyncio
async def test_coalesce_fills_null(db_session):
    t1 = await _seed_totalizer(db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0)])  # delta None
    node = {
        "op": "coalesce",
        "args": [
            {
                "op": "agg",
                "source": {"type": "tag", "tag_id": t1.id},
                "agg": "delta",
                "window": "2d",
            },
            {"op": "const", "value": 0.0},
        ],
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.scalar == 0.0


@pytest.mark.asyncio
async def test_reduce_avg_of_daily_delta(db_session):
    t1 = await _seed_totalizer(
        db_session,
        "T1",
        [
            (datetime(2026, 6, 1, 0), 0.0),
            (datetime(2026, 6, 1, 23), 40.0),
            (datetime(2026, 6, 2, 0), 40.0),
            (datetime(2026, 6, 2, 23), 80.0),
        ],
    )
    node = {
        "op": "reduce",
        "source": {
            "op": "series",
            "source": {"type": "tag", "tag_id": t1.id},
            "agg": "delta",
            "grain": "day",
            "window": "2d",
        },
        "reduce": "avg",
    }
    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=_noref,
    )
    assert res.kind == "scalar"
    assert res.scalar == 40.0


@pytest.mark.asyncio
async def test_ref_resolves_via_callback(db_session):
    node = {"op": "ref", "variable_id": 7}

    async def resolve(vid):
        assert vid == 7
        return EvalResult(kind="scalar", scalar=123.0, series=None)

    res = await evaluate(
        db_session,
        node,
        start=JUNE[0],
        end=JUNE[1],
        grain="day",
        tz_offset_hours=0,
        resolve_ref=resolve,
    )
    assert res.scalar == 123.0
