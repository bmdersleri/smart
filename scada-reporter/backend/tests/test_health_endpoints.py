"""Tests for /live, /ready, and /health endpoints (Task 7 — liveness/readiness).

Coverage:
- /live   : always 200 {"status": "alive"}
- /ready  : happy path → 200; DB down → 503; alembic mismatch → 503; no scheduler → 503
- /health : regression (original keys) + new collector_running / scheduler_running keys
- Unit: alembic_head_matches tolerance (no alembic_version table → True)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import app.api.health as health_api

# ── /live ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_always_200(client: AsyncClient):
    resp = await client.get("/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


# ── /ready ────────────────────────────────────────────────────────────────────


def _running_scheduler():
    """A fake scheduler whose .running attribute is True."""
    return SimpleNamespace(running=True)


@pytest.mark.asyncio
async def test_ready_happy_path(client: AsyncClient):
    """All checks pass → 200 with all checks True."""
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=True)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=True)),
        patch("app.api.health.get_scheduler", return_value=_running_scheduler()),
        patch.object(health_api.settings, "RUN_SCHEDULER", True),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["role"]["scheduler_enabled"] is True
    assert data["checks"]["db"] is True
    assert data["checks"]["alembic_head"] is True
    assert data["checks"]["scheduler"] is True


@pytest.mark.asyncio
async def test_ready_db_down(client: AsyncClient):
    """DB unreachable → 503 with db check False."""
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=False)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=True)),
        patch("app.api.health.get_scheduler", return_value=_running_scheduler()),
        patch.object(health_api.settings, "RUN_SCHEDULER", True),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["db"] is False


@pytest.mark.asyncio
async def test_ready_alembic_mismatch(client: AsyncClient):
    """Alembic head differs from DB → 503 with alembic_head False."""
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=True)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=False)),
        patch("app.api.health.get_scheduler", return_value=_running_scheduler()),
        patch.object(health_api.settings, "RUN_SCHEDULER", True),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["alembic_head"] is False


@pytest.mark.asyncio
async def test_ready_scheduler_not_running_none(client: AsyncClient):
    """get_scheduler() returns None → scheduler check False → 503."""
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=True)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=True)),
        patch("app.api.health.get_scheduler", return_value=None),
        patch.object(health_api.settings, "RUN_SCHEDULER", True),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["checks"]["scheduler"] is False


@pytest.mark.asyncio
async def test_ready_scheduler_not_running_false(client: AsyncClient):
    """Scheduler exists but .running is False → 503."""
    stopped_sched = SimpleNamespace(running=False)
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=True)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=True)),
        patch("app.api.health.get_scheduler", return_value=stopped_sched),
        patch.object(health_api.settings, "RUN_SCHEDULER", True),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["checks"]["scheduler"] is False


@pytest.mark.asyncio
async def test_ready_scheduler_disabled_is_ignored(client: AsyncClient):
    """RUN_SCHEDULER=False → scheduler check is marked disabled and does not fail readiness."""
    with (
        patch("app.api.health.db_ok", new=AsyncMock(return_value=True)),
        patch("app.api.health.alembic_head_matches", new=AsyncMock(return_value=True)),
        patch("app.api.health.get_scheduler") as get_scheduler_mock,
        patch.object(health_api.settings, "RUN_SCHEDULER", False),
    ):
        resp = await client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"]["scheduler_enabled"] is False
    assert data["checks"]["scheduler"] == "disabled"
    get_scheduler_mock.assert_not_called()


# ── /health (regression + new fields) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_preserves_original_keys(client: AsyncClient):
    """/health still returns the original shape (regression guard)."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    # Original keys
    assert "status" in data
    assert "plc_connected" in data
    assert "plc_total" in data
    assert "plcs" in data


@pytest.mark.asyncio
async def test_health_new_fields(client: AsyncClient):
    """/health now also returns collector_running and scheduler_running."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "collector_running" in data
    assert "scheduler_enabled" in data
    assert "scheduler_running" in data
    assert isinstance(data["collector_running"], bool)
    assert isinstance(data["scheduler_enabled"], bool)
    assert isinstance(data["scheduler_running"], bool)


@pytest.mark.asyncio
async def test_health_uptime_fields(client: AsyncClient):
    """/health returns uptime_seconds (float >= 0) and started_at (ISO 8601)."""
    from datetime import datetime

    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "uptime_seconds" in data
    assert "started_at" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0.0
    # started_at must parse as a tz-aware datetime
    parsed = datetime.fromisoformat(data["started_at"])
    assert parsed.tzinfo is not None


# ── Unit: alembic_head_matches tolerance ─────────────────────────────────────


@pytest.mark.asyncio
async def test_alembic_head_matches_no_version_table(monkeypatch):
    """When no alembic_version table exists (create_all dev/test), return True."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    import app.core.database
    from app.core.database import Base
    from app.core.db_health import alembic_head_matches

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(app.core.database, "engine", engine)
    try:
        result = await alembic_head_matches()
        assert result is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_alembic_head_matches_unexpected_error_returns_false():
    """Unexpected Alembic probe errors fail closed instead of masking readiness issues."""
    from unittest.mock import patch

    from app.core.db_health import alembic_head_matches

    with patch("alembic.script.ScriptDirectory.from_config", side_effect=RuntimeError("boom")):
        result = await alembic_head_matches()

    assert result is False
