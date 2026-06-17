"""Period-comparison backing endpoint: trend_range with explicit start/end."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag, TagReading
from app.models.user import User


async def _admin(client: AsyncClient, db: AsyncSession, username: str) -> str:
    db.add(
        User(
            username=username,
            email=f"{username}@t.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_trend_range_returns_only_window(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "range_user")
    h = {"Authorization": f"Bearer {tok}"}
    tag = Tag(node_id="RNG,REAL0", name="RngTag", unit="m3", long_term=True)
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    base = datetime(2026, 6, 1, 12, 0, 0)
    # points at 0,1,2,3,4 hours
    for i in range(5):
        db_session.add(
            TagReading(
                tag_id=tag.id, value=float(i), quality=192, timestamp=base + timedelta(hours=i)
            )
        )
    await db_session.commit()

    start = (base + timedelta(hours=1)).isoformat()
    end = (base + timedelta(hours=3)).isoformat()
    r = await client.get(
        "/api/dashboard/trend_range",
        params={"tag_ids": [tag.id], "start": start, "end": end},
        headers=h,
    )
    assert r.status_code == 200
    series = r.json()
    assert len(series) == 1
    values = [p["v"] for p in series[0]["data"]]
    # only hours 1,2,3 in window
    assert values == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
async def test_trend_range_empty_window(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin(client, db_session, "range_empty")
    h = {"Authorization": f"Bearer {tok}"}
    tag = Tag(node_id="RNG2,REAL0", name="RngTag2", long_term=True)
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    now = datetime.now(UTC)
    start = (now - timedelta(hours=2)).isoformat()
    end = (now - timedelta(hours=1)).isoformat()
    r = await client.get(
        "/api/dashboard/trend_range",
        params={"tag_ids": [tag.id], "start": start, "end": end},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json() == []
