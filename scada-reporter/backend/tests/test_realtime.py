"""SSE canlı-değer akışı: generator + /dashboard/stream endpoint."""

import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.api.realtime import latest_event_stream
from app.collector.cache import latest_cache


def _parse(frame: str) -> dict:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame[len("data: ") :].strip())


@pytest.mark.asyncio
async def test_stream_yields_requested_tag_values():
    latest_cache.update(50101, 12.5, 192, datetime.now(UTC))
    frames = [f async for f in latest_event_stream([50101], interval=0.01, max_events=1)]
    assert len(frames) == 1
    data = _parse(frames[0])
    assert data["50101"]["v"] == 12.5
    assert data["50101"]["q"] == 192
    assert "t" in data["50101"]


@pytest.mark.asyncio
async def test_stream_empty_tag_ids_returns_all_cached():
    latest_cache.update(50202, 7.0, 0, datetime.now(UTC))
    frames = [f async for f in latest_event_stream([], interval=0.01, max_events=1)]
    data = _parse(frames[0])
    assert "50202" in data


@pytest.mark.asyncio
async def test_stream_emits_multiple_events():
    frames = [f async for f in latest_event_stream([], interval=0.001, max_events=3)]
    assert len(frames) == 3


async def _token(client: AsyncClient, db) -> str:
    from app.core.security import hash_password
    from app.models.user import User

    db.add(
        User(
            username="sse", email="s@t.com", hashed_password=hash_password("test123"), role="admin"
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": "sse", "password": "test123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_stream_endpoint_requires_valid_token(client: AsyncClient):
    r = await client.get("/api/dashboard/stream", params={"token": "garbage", "limit": 1})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_stream_endpoint_serves_event_stream(client: AsyncClient, db_session):
    latest_cache.update(50303, 3.3, 192, datetime.now(UTC))
    token = await _token(client, db_session)
    r = await client.get(
        "/api/dashboard/stream",
        params={"token": token, "tag_ids": [50303], "limit": 1},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    data = _parse(r.text)
    assert data["50303"]["v"] == 3.3
