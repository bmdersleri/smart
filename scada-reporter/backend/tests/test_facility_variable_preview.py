from datetime import datetime

import pytest

from app.services.facility_variables.preview import (
    PreviewBoundsError,
    check_preview_bounds,
    estimate_points,
    preview_variable,
)
from app.services.facility_variables.service import create_variable


def test_estimate_points_minute_year_is_huge():
    n = estimate_points(datetime(2026, 1, 1), datetime(2027, 1, 1), "hour")
    assert n >= 8000


def test_check_bounds_rejects_oversized():
    with pytest.raises(PreviewBoundsError):
        check_preview_bounds(datetime(2026, 1, 1), datetime(2027, 1, 1), "hour")


def test_check_bounds_allows_month_daily():
    check_preview_bounds(datetime(2026, 6, 1), datetime(2026, 7, 1), "day")  # no raise


@pytest.mark.asyncio
async def test_preview_scalar(db_session):
    var = await create_variable(
        db_session,
        code="p1",
        name="p1",
        description="",
        kind="scalar",
        unit="m3/gun",
        expression={"op": "const", "value": 42.0},
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )
    out = await preview_variable(
        db_session,
        var,
        start=datetime(2026, 6, 1),
        end=datetime(2026, 7, 1),
        grain="day",
        tz_offset_hours=3,
    )
    assert out["kind"] == "scalar"
    assert out["value"] == 42.0
    assert out["unit"] == "m3/gun"


@pytest.mark.asyncio
async def test_preview_series_emits_offset_ts(db_session):
    from app.models.tag import Tag, TagReading

    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 0), value=0.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 18), value=40.0))
    await db_session.commit()

    var = await create_variable(
        db_session,
        code="p2",
        name="p2",
        description="",
        kind="series",
        unit="m3/gun",
        expression={
            "op": "series",
            "source": {"type": "tag", "tag_id": tag.id},
            "agg": "delta",
            "grain": "day",
            "window": "2d",
        },
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
        value_type="number",
        created_by=1,
    )
    out = await preview_variable(
        db_session,
        var,
        start=datetime(2026, 6, 1),
        end=datetime(2026, 6, 3),
        grain="day",
        tz_offset_hours=3,
    )
    assert out["kind"] == "series"
    assert out["points"][0]["ts"].endswith("+03:00")
    assert out["points"][0]["value"] == 40.0
