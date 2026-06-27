from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

import app.api.runtime as runtime_api
from app.api.auth import get_current_user
from app.main import app


def _user(role: str):
    return SimpleNamespace(
        id=1,
        username=role,
        role=role,
        permission_overrides={},
        is_active=True,
    )


def _status(*, collector_running: bool = False, scheduler_running: bool = False):
    return {
        "controls_enabled": True,
        "backend": {
            "status": "ok",
            "uptime_seconds": 1.0,
            "started_at": "2026-06-27T08:00:00+00:00",
        },
        "collector": {
            "configured": True,
            "running": collector_running,
            "poller_running": collector_running,
            "opcua_running": False,
            "monitor_running": collector_running,
        },
        "scheduler": {
            "configured": True,
            "running": scheduler_running,
        },
    }


@pytest_asyncio.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_runtime_status_is_admin_only(client):
    app.dependency_overrides[get_current_user] = lambda: _user("operator")
    try:
        resp = await client.get("/api/runtime/status")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_runtime_status_returns_collector_and_scheduler_state(client, as_admin, monkeypatch):
    monkeypatch.setattr(
        runtime_api,
        "runtime_status",
        Mock(return_value=_status(collector_running=True, scheduler_running=False)),
    )

    resp = await client.get("/api/runtime/status")

    assert resp.status_code == 200
    assert resp.json()["collector"]["running"] is True
    assert resp.json()["scheduler"]["running"] is False


@pytest.mark.asyncio
async def test_runtime_collector_start_stop(client, as_admin, monkeypatch):
    start_collector = AsyncMock()
    stop_collector = AsyncMock()
    status = Mock(
        side_effect=[
            _status(collector_running=True),
            _status(collector_running=False),
        ]
    )
    monkeypatch.setattr(runtime_api, "start_collector", start_collector)
    monkeypatch.setattr(runtime_api, "stop_collector", stop_collector)
    monkeypatch.setattr(runtime_api, "runtime_status", status)

    start_resp = await client.post("/api/runtime/collector/start")
    stop_resp = await client.post("/api/runtime/collector/stop")

    assert start_resp.status_code == 200
    assert start_resp.json()["collector"]["running"] is True
    assert stop_resp.status_code == 200
    assert stop_resp.json()["collector"]["running"] is False
    start_collector.assert_awaited_once()
    stop_collector.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_scheduler_start_stop(client, as_admin, monkeypatch):
    start_scheduler = AsyncMock()
    stop_scheduler = Mock()
    status = Mock(
        side_effect=[
            _status(scheduler_running=True),
            _status(scheduler_running=False),
        ]
    )
    monkeypatch.setattr(runtime_api, "start_runtime_scheduler", start_scheduler)
    monkeypatch.setattr(runtime_api, "stop_runtime_scheduler", stop_scheduler)
    monkeypatch.setattr(runtime_api, "runtime_status", status)

    start_resp = await client.post("/api/runtime/scheduler/start")
    stop_resp = await client.post("/api/runtime/scheduler/stop")

    assert start_resp.status_code == 200
    assert start_resp.json()["scheduler"]["running"] is True
    assert stop_resp.status_code == 200
    assert stop_resp.json()["scheduler"]["running"] is False
    start_scheduler.assert_awaited_once()
    stop_scheduler.assert_called_once()
