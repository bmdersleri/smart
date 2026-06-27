from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.scheduler.runner as scheduler_runner


@pytest.mark.asyncio
async def test_scheduler_runner_refuses_invalid_config(monkeypatch):
    start_scheduler = AsyncMock()
    monkeypatch.setattr(scheduler_runner, "start_scheduler", start_scheduler)
    monkeypatch.setattr(
        type(scheduler_runner.settings),
        "config_errors",
        lambda self: ["bad config"],
    )

    with pytest.raises(RuntimeError, match="Production yapılandırma hatası"):
        await scheduler_runner.main()

    start_scheduler.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_runner_requires_scheduler_role(monkeypatch):
    start_scheduler = AsyncMock()
    monkeypatch.setattr(scheduler_runner, "start_scheduler", start_scheduler)
    monkeypatch.setattr(type(scheduler_runner.settings), "config_errors", lambda self: [])
    monkeypatch.setattr(scheduler_runner.settings, "RUN_SCHEDULER", False)

    with pytest.raises(RuntimeError, match="RUN_SCHEDULER=True"):
        await scheduler_runner.main()

    start_scheduler.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_runner_starts_and_shuts_down(monkeypatch):
    start_scheduler = AsyncMock()
    shutdown = Mock()
    fake_scheduler = SimpleNamespace(shutdown=shutdown)

    monkeypatch.setattr(scheduler_runner, "start_scheduler", start_scheduler)
    monkeypatch.setattr(scheduler_runner, "get_scheduler", lambda: fake_scheduler)
    monkeypatch.setattr(type(scheduler_runner.settings), "config_errors", lambda self: [])
    monkeypatch.setattr(type(scheduler_runner.settings), "config_warnings", lambda self: [])
    monkeypatch.setattr(
        scheduler_runner,
        "_install_shutdown_handlers",
        lambda stop_event: stop_event.set(),
    )

    await scheduler_runner.main()

    start_scheduler.assert_awaited_once_with(scheduler_runner.settings.DATABASE_URL)
    shutdown.assert_called_once_with(wait=False)
