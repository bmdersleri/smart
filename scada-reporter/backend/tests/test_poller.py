"""Poller: ayarlar, grup okuma, bulk yazma, tek-tick koşusu."""

import asyncio

import pytest

from app.collector import poller
from app.collector.s7_collector import ReadSpec
from app.core.config import settings


def test_settings_worker_pool_covers_fleet():
    assert settings.S7_MAX_WORKERS >= 27  # 27 PLC filosu
    assert settings.S7_PLC_READ_TIMEOUT > 0


@pytest.mark.asyncio
async def test_read_plc_group_success(monkeypatch):
    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(1.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)
    items = [
        (11, ReadSpec("DB", 1, 0, 0, 4, "REAL")),
        (22, ReadSpec("DB", 1, 4, 0, 2, "WORD")),
    ]
    out = await poller.read_plc_group(("10.0.0.1", 0, 1), items, timeout=5)
    assert out == [(11, 1.0, 192), (22, 1.0, 192)]


@pytest.mark.asyncio
async def test_read_plc_group_timeout_marks_bad(monkeypatch):
    async def slow(ip, rack, slot, specs, name=""):
        await asyncio.sleep(10)

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", slow)
    items = [(11, ReadSpec("DB", 1, 0, 0, 4, "REAL"))]
    out = await poller.read_plc_group(("10.0.0.1", 0, 1), items, timeout=0.05)
    assert out == [(11, None, 0)]
