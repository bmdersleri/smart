from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.buckets import bucket_series
from app.services.template_fill.daily_rollup import daily_values


@pytest.mark.asyncio
@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max", "last", "delta"])
async def test_bucket_series_matches_daily_values(db_session, agg):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # spread readings across June 1-3 with multiple per day
    rows = [
        (datetime(2026, 6, 1, 1), 10.0),
        (datetime(2026, 6, 1, 13), 30.0),
        (datetime(2026, 6, 1, 22), 55.0),
        (datetime(2026, 6, 2, 2), 60.0),
        (datetime(2026, 6, 2, 20), 90.0),
        (datetime(2026, 6, 3, 5), 95.0),
        (datetime(2026, 6, 3, 18), 120.0),
    ]
    for ts, val in rows:
        db_session.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db_session.commit()

    offset = 3
    legacy = await daily_values(db_session, tag.id, 2026, 6, agg, tz_offset_hours=offset)
    engine_out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 7, 1), "day", agg, offset
    )
    # re-key engine output {date -> v} to {day_no -> v} for comparison
    engine_by_day = {k.day: v for k, v in engine_out.items()}
    assert engine_by_day == legacy
