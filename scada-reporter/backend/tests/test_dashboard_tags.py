"""Dashboard /tags endpoint: filtering, quality, pagination."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag, TagReading
from app.models.user import User


async def _register_and_login(client: AsyncClient, db: AsyncSession, username: str) -> str:
    user = User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=hash_password("pw123"),
        full_name=username,
    )
    db.add(user)
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


async def _make_tag(
    db: AsyncSession,
    name: str,
    device: str = "DT_DEV1",
    daily: bool = False,
    interval: int = 5,
    description: str = "",
) -> int:
    tag = Tag(
        node_id=f"ns=2;s={name}",
        name=name,
        device=device,
        long_term=True,
        daily_tracking=daily,
        sample_interval=interval,
        description=description,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag.id


@pytest.mark.asyncio
async def test_filter_device(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_dev_user")
    await _make_tag(db_session, "DT_DEV_TAG1", device="DT_ALPHA")
    await _make_tag(db_session, "DT_DEV_TAG2", device="DT_BETA")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/dashboard/tags", params={"device": "DT_ALPHA"}, headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["device"] == "DT_ALPHA" for i in items)
    names = [i["name"] for i in items]
    assert "DT_DEV_TAG1" in names
    assert "DT_DEV_TAG2" not in names


@pytest.mark.asyncio
async def test_filter_search(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_search_user")
    await _make_tag(db_session, "DT_PUMP_FLOW", device="DT_SEARCH_DEV")
    await _make_tag(db_session, "DT_PUMP_PRESSURE", device="DT_SEARCH_DEV")
    await _make_tag(db_session, "DT_MOTOR_SPEED", device="DT_SEARCH_DEV")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/dashboard/tags", params={"search": "PUMP"}, headers=headers)
    names = [i["name"] for i in r.json()["items"]]
    assert "DT_PUMP_FLOW" in names
    assert "DT_PUMP_PRESSURE" in names
    assert "DT_MOTOR_SPEED" not in names


@pytest.mark.asyncio
async def test_filter_daily(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_daily_user")
    await _make_tag(db_session, "DT_DAILY_YES", device="DT_DAILY_DEV", daily=True)
    await _make_tag(db_session, "DT_DAILY_NO", device="DT_DAILY_DEV", daily=False)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        "/api/dashboard/tags", params={"device": "DT_DAILY_DEV", "daily": "true"}, headers=headers
    )
    names = [i["name"] for i in r.json()["items"]]
    assert "DT_DAILY_YES" in names
    assert "DT_DAILY_NO" not in names


@pytest.mark.asyncio
async def test_quality_good(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_good_user")
    tag_good = await _make_tag(db_session, "DT_GOOD_TAG", device="DT_QUAL_DEV")
    tag_bad = await _make_tag(db_session, "DT_BAD_TAG", device="DT_QUAL_DEV")

    ts = datetime.now(UTC)
    db_session.add(TagReading(tag_id=tag_good, value=1.0, quality=192, timestamp=ts))
    db_session.add(TagReading(tag_id=tag_bad, value=2.0, quality=0, timestamp=ts))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        "/api/dashboard/tags", params={"device": "DT_QUAL_DEV", "quality": "good"}, headers=headers
    )
    names = [i["name"] for i in r.json()["items"]]
    assert "DT_GOOD_TAG" in names
    assert "DT_BAD_TAG" not in names


@pytest.mark.asyncio
async def test_quality_bad(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_bad_user")
    tag_good = await _make_tag(db_session, "DT_BGOOD_TAG", device="DT_BQUAL_DEV")
    tag_bad = await _make_tag(db_session, "DT_BBAD_TAG", device="DT_BQUAL_DEV")

    ts = datetime.now(UTC)
    db_session.add(TagReading(tag_id=tag_good, value=1.0, quality=192, timestamp=ts))
    db_session.add(TagReading(tag_id=tag_bad, value=2.0, quality=0, timestamp=ts))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        "/api/dashboard/tags", params={"device": "DT_BQUAL_DEV", "quality": "bad"}, headers=headers
    )
    names = [i["name"] for i in r.json()["items"]]
    assert "DT_BBAD_TAG" in names
    assert "DT_BGOOD_TAG" not in names


@pytest.mark.asyncio
async def test_quality_stale(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_stale_user")
    tag_fresh = await _make_tag(db_session, "DT_FRESH_TAG", device="DT_STALE_DEV", interval=5)
    tag_stale = await _make_tag(db_session, "DT_STALE_TAG", device="DT_STALE_DEV", interval=5)

    now = datetime.now(UTC)
    db_session.add(TagReading(tag_id=tag_fresh, value=1.0, quality=192, timestamp=now))
    db_session.add(
        TagReading(tag_id=tag_stale, value=2.0, quality=192, timestamp=now - timedelta(seconds=20))
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        "/api/dashboard/tags",
        params={"device": "DT_STALE_DEV", "quality": "stale"},
        headers=headers,
    )
    names = [i["name"] for i in r.json()["items"]]
    assert "DT_STALE_TAG" in names
    assert "DT_FRESH_TAG" not in names


@pytest.mark.asyncio
async def test_pagination(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_page_user")
    for i in range(60):
        await _make_tag(db_session, f"DT_PAGE_TAG_{i:03d}", device="DT_PAGE_DEV")
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.get(
        "/api/dashboard/tags",
        params={"device": "DT_PAGE_DEV", "page": 1, "page_size": 50},
        headers=headers,
    )
    data1 = r1.json()
    assert data1["total"] == 60
    assert len(data1["items"]) == 50
    assert data1["total_pages"] == math.ceil(60 / 50)

    r2 = await client.get(
        "/api/dashboard/tags",
        params={"device": "DT_PAGE_DEV", "page": 2, "page_size": 50},
        headers=headers,
    )
    data2 = r2.json()
    assert len(data2["items"]) == 10
    assert data2["page"] == 2


@pytest.mark.asyncio
async def test_latest_reading_picks_newest(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_latest_user")
    tid = await _make_tag(db_session, "DT_LATEST_TAG", device="DT_LATEST_DEV")
    now = datetime.now(UTC)
    db_session.add(
        TagReading(tag_id=tid, value=1.0, quality=192, timestamp=now - timedelta(seconds=30))
    )
    db_session.add(TagReading(tag_id=tid, value=2.0, quality=192, timestamp=now))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/dashboard/tags", params={"device": "DT_LATEST_DEV"}, headers=headers)
    item = next(i for i in r.json()["items"] if i["name"] == "DT_LATEST_TAG")
    assert item["value"] == 2.0
    assert item["quality_ok"] is True


@pytest.mark.asyncio
async def test_items_include_description(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "dt_desc_user")
    await _make_tag(
        db_session, "DT_DESC_TAG", device="DT_DESC_DEV", description="Inlet channel flow"
    )
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/dashboard/tags", params={"device": "DT_DESC_DEV"}, headers=headers)
    item = next(i for i in r.json()["items"] if i["name"] == "DT_DESC_TAG")
    assert item["description"] == "Inlet channel flow"
