from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.main as main_mod


class _FakeConn:
    async def execution_options(self, **kwargs):
        return self


class _FakeCtx:
    def __init__(self):
        self.conn = _FakeConn()

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def begin(self):
        return _FakeCtx()

    def connect(self):
        return _FakeCtx()


@pytest.mark.asyncio
async def test_lifespan_skips_scheduler_when_disabled(monkeypatch):
    start_scheduler = AsyncMock()
    monkeypatch.setattr(main_mod, "start_scheduler", start_scheduler)
    monkeypatch.setattr(main_mod, "init_database_schema", AsyncMock())
    monkeypatch.setattr(main_mod, "init_continuous_aggregates", AsyncMock())
    monkeypatch.setattr(main_mod, "init_daily_rollup", AsyncMock())
    monkeypatch.setattr(
        main_mod,
        "initialize_license_state",
        lambda settings: SimpleNamespace(info=None, mode=SimpleNamespace(value="demo")),
    )
    monkeypatch.setattr(main_mod, "engine", _FakeEngine())
    monkeypatch.setattr(main_mod.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod.settings, "RUN_COLLECTOR", False)
    monkeypatch.setattr(main_mod.settings, "RUN_SCHEDULER", False)

    async with main_mod.lifespan(main_mod.app):
        pass

    start_scheduler.assert_not_awaited()


@pytest.mark.asyncio
async def test_lifespan_starts_scheduler_when_enabled(monkeypatch):
    start_scheduler = AsyncMock()
    monkeypatch.setattr(main_mod, "start_scheduler", start_scheduler)
    monkeypatch.setattr(main_mod, "init_database_schema", AsyncMock())
    monkeypatch.setattr(main_mod, "init_continuous_aggregates", AsyncMock())
    monkeypatch.setattr(main_mod, "init_daily_rollup", AsyncMock())
    monkeypatch.setattr(
        main_mod,
        "initialize_license_state",
        lambda settings: SimpleNamespace(info=None, mode=SimpleNamespace(value="demo")),
    )
    monkeypatch.setattr(main_mod, "engine", _FakeEngine())
    monkeypatch.setattr(main_mod.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod.settings, "RUN_COLLECTOR", False)
    monkeypatch.setattr(main_mod.settings, "RUN_SCHEDULER", True)

    async with main_mod.lifespan(main_mod.app):
        pass

    start_scheduler.assert_awaited_once_with(main_mod.settings.DATABASE_URL)
