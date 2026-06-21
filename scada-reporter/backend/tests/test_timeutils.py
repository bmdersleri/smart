"""Timezone-aware serialization: as_utc/utc_iso + endpoint offset."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.timeutils import as_utc, utc_iso
from app.models.tag import Tag, TagReading
from app.models.user import User


def test_as_utc_naive_assumed_utc():
    naive = datetime(2026, 6, 20, 14, 0, 0)
    out = as_utc(naive)
    assert out.tzinfo is not None
    assert out.utcoffset() == timedelta(0)


def test_as_utc_aware_converted_to_utc():
    aware = datetime(2026, 6, 20, 17, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    out = as_utc(aware)
    assert out.utcoffset() == timedelta(0)
    assert out.hour == 14  # 17:00+03:00 == 14:00 UTC


def test_as_utc_none():
    assert as_utc(None) is None
    assert utc_iso(None) is None


def test_utc_iso_has_offset():
    iso = utc_iso(datetime(2026, 6, 20, 14, 0, 0))
    assert iso is not None
    assert iso.endswith("+00:00")


@pytest.mark.asyncio
async def test_trend_timestamps_carry_offset(client: AsyncClient, db_session: AsyncSession):
    """Trend series timestamps must serialize with an explicit UTC offset."""
    db_session.add(
        User(username="tz", email="tz@t.com", hashed_password=hash_password("pw123"), role="admin")
    )
    await db_session.commit()
    tok = (
        await client.post("/api/auth/token", data={"username": "tz", "password": "pw123"})
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    tag = Tag(node_id="TZ,DD0", name="TzTag", sample_interval=5)
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    now = datetime.now(UTC)
    db_session.add(TagReading(tag_id=tag.id, value=1.0, quality=192, timestamp=now))
    await db_session.commit()

    body = (
        await client.get(
            "/api/dashboard/trend",
            params={"tag_ids": tag.id, "hours": 1},
            headers=h,
        )
    ).json()
    points = body[0]["data"]
    assert points, "expected at least one trend point"
    ts = points[0]["t"]
    assert ts.endswith("+00:00") or ts.endswith("Z"), f"timestamp lacks UTC offset: {ts}"
