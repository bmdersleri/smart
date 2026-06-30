from datetime import datetime

import pytest
import pytest_asyncio

from app.models.tag import Tag, TagReading
from app.services.template_fill.daily_rollup import daily_values, reduce_values


def test_delta_clamps_negative_to_zero():
    # delta = tüketim; kümülatif sayaç düşerse (reset/glitch) negatif anlamsız → 0'a kırp
    assert reduce_values([15.611, 15.565], "delta") == 0.0
    # normal pozitif tüketim değişmez
    assert reduce_values([10.0, 12.0, 12.5], "delta") == 2.5
    # <2 nokta → None (değişmez)
    assert reduce_values([5.0], "delta") is None


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(db_session):
    # In-memory engine is session-scoped, so wipe this module's tables
    # between tests to keep node_id fixtures from colliding.
    yield
    await db_session.execute(TagReading.__table__.delete())
    await db_session.execute(Tag.__table__.delete())
    await db_session.commit()


@pytest_asyncio.fixture
async def tag_with_readings(db_session):
    tag = Tag(node_id="n1", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.flush()
    rows = [
        TagReading(tag_id=tag.id, value=10.0, timestamp=datetime(2026, 5, 1, 1, 0)),
        TagReading(tag_id=tag.id, value=20.0, timestamp=datetime(2026, 5, 1, 8, 0)),
        TagReading(tag_id=tag.id, value=30.0, timestamp=datetime(2026, 5, 1, 20, 0)),
        TagReading(tag_id=tag.id, value=5.0, timestamp=datetime(2026, 5, 2, 12, 0)),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return tag


@pytest.mark.asyncio
async def test_sum_avg_min_max(db_session, tag_with_readings):
    tag = tag_with_readings
    assert await daily_values(db_session, tag.id, 2026, 5, "sum") == {1: 60.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "avg") == {1: 20.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "min") == {1: 10.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "max") == {1: 30.0, 2: 5.0}


@pytest.mark.asyncio
async def test_last_and_delta(db_session, tag_with_readings):
    tag = tag_with_readings
    assert await daily_values(db_session, tag.id, 2026, 5, "last") == {1: 30.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "delta") == {1: 20.0}


@pytest.mark.asyncio
async def test_tz_offset_shifts_day(db_session):
    tag = Tag(node_id="n2", name="X", unit="")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(TagReading(tag_id=tag.id, value=7.0, timestamp=datetime(2026, 5, 1, 23, 0)))
    await db_session.commit()
    result = await daily_values(db_session, tag.id, 2026, 5, "last", tz_offset_hours=3)
    assert result == {2: 7.0}


@pytest.mark.asyncio
async def test_unknown_agg_raises(db_session):
    tag = Tag(node_id="n3", name="Y", unit="")
    db_session.add(tag)
    await db_session.flush()
    await db_session.commit()
    with pytest.raises(ValueError):
        await daily_values(db_session, tag.id, 2026, 5, "median")
