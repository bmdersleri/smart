from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.buckets import agg_window, bucket_series


@pytest.mark.asyncio
async def test_agg_window_delta(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # totalizer: 10 at 00:00, 30 at 12:00, 50 at 23:00 → delta = 40
    for hh, val in ((0, 10.0), (12, 30.0), (23, 50.0)):
        db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, hh), value=val))
    await db_session.commit()

    out = await agg_window(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 2), "delta", 0
    )
    assert out == 40.0


@pytest.mark.asyncio
async def test_bucket_series_daily_delta(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # day 1: 10→50 (delta 40); day 2: 50→90 (delta 40)
    rows = [
        (datetime(2026, 6, 1, 0), 10.0),
        (datetime(2026, 6, 1, 23), 50.0),
        (datetime(2026, 6, 2, 0), 50.0),
        (datetime(2026, 6, 2, 23), 90.0),
    ]
    for ts, val in rows:
        db_session.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db_session.commit()

    out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 3), "day", "delta", 0
    )
    assert out[datetime(2026, 6, 1)] == 40.0
    assert out[datetime(2026, 6, 2)] == 40.0


@pytest.mark.asyncio
async def test_bucket_series_respects_tz_offset(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # 22:00 UTC on May 31 == 01:00 Jun 1 at +3 → belongs to Jun 1 local bucket
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 5, 31, 22), value=5.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 5), value=9.0))
    await db_session.commit()

    out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 2), "day", "last", 3
    )
    # both readings fall in the Jun 1 local day; last = 9.0
    assert out[datetime(2026, 6, 1)] == 9.0
