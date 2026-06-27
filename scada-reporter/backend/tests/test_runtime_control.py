import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.runtime_control import CollectorRuntime


async def _forever():
    while True:
        await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_collector_stop_is_idempotent_without_started_opcua(monkeypatch):
    runtime = CollectorRuntime()
    stop = AsyncMock()
    disconnect = AsyncMock()

    monkeypatch.setattr("app.services.runtime_control.opcua_server", SimpleNamespace(stop=stop))
    monkeypatch.setattr(
        "app.services.runtime_control.plc_manager",
        SimpleNamespace(disconnect_all=disconnect),
    )

    status = await runtime.stop()

    assert status["running"] is False
    stop.assert_not_awaited()
    disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_collector_status_reports_opcua_running_flag(monkeypatch):
    runtime = CollectorRuntime(opcua_running=True)
    stop = AsyncMock()
    disconnect = AsyncMock()

    monkeypatch.setattr("app.services.runtime_control.opcua_server", SimpleNamespace(stop=stop))
    monkeypatch.setattr(
        "app.services.runtime_control.plc_manager",
        SimpleNamespace(disconnect_all=disconnect),
    )

    assert runtime.status()["opcua_running"] is True

    status = await runtime.stop()

    assert status["opcua_running"] is False
    stop.assert_awaited_once()
    disconnect.assert_awaited_once()
