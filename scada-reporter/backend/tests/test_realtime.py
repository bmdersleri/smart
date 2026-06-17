"""SSE canlı-değer akışı: generator + /dashboard/stream endpoint."""

import json
import logging
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.api.realtime import latest_event_stream, log_event_stream
from app.collector.cache import latest_cache
from app.core.log_buffer import log_buffer


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


# --- Log stream tests ---


def _parse_list(frame: str) -> list:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame[len("data: ") :].strip())


@pytest.mark.asyncio
async def test_log_stream_yields_buffered_lines():
    log_buffer.emit(
        logging.LogRecord("app.poller", logging.INFO, __file__, 1, "tick ok", None, None)
    )
    frames = [f async for f in log_event_stream(interval=0.01, max_events=1)]
    assert len(frames) == 1
    rows = _parse_list(frames[0])
    assert any(r["msg"] == "tick ok" and r["level"] == "INFO" for r in rows)


@pytest.mark.asyncio
async def test_log_stream_min_level_excludes_info():
    log_buffer.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "noise-info", None, None))
    log_buffer.emit(logging.LogRecord("x", logging.WARNING, __file__, 1, "real-warn", None, None))
    frames = [
        f async for f in log_event_stream(min_level=logging.WARNING, interval=0.01, max_events=1)
    ]
    rows = _parse_list(frames[0])
    msgs = [r["msg"] for r in rows]
    assert "real-warn" in msgs
    assert "noise-info" not in msgs


@pytest.mark.asyncio
async def test_logs_stream_endpoint_requires_valid_token(client: AsyncClient):
    r = await client.get("/api/dashboard/logs/stream", params={"token": "garbage", "limit": 1})
    assert r.status_code == 401


async def _log_token(client: AsyncClient, db) -> str:
    from app.core.security import hash_password
    from app.models.user import User

    db.add(
        User(
            username="sse_log",
            email="sse_log@t.com",
            hashed_password=hash_password("test123"),
            role="admin",
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": "sse_log", "password": "test123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_logs_stream_endpoint_serves_event_stream(client: AsyncClient, db_session):
    log_buffer.emit(
        logging.LogRecord("app", logging.INFO, __file__, 1, "endpoint-line", None, None)
    )
    token = await _log_token(client, db_session)
    r = await client.get("/api/dashboard/logs/stream", params={"token": token, "limit": 1})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    rows = _parse_list(r.text)
    assert any(x["msg"] == "endpoint-line" for x in rows)
