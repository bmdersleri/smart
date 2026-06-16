"""Poller: ayarlar, grup okuma, bulk yazma, tek-tick koşusu."""

import asyncio
from datetime import UTC, datetime

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collector import poller
from app.collector.s7_collector import ReadSpec
from app.core.config import settings
from app.models.tag import Tag, TagReading


def _sample(name: str, labels: dict | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


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


@pytest.mark.asyncio
async def test_write_readings_bulk(db_engine):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t1 = Tag(node_id="ns=2;s=WR1", name="WR1", long_term=True)
        t2 = Tag(node_id="ns=2;s=WR2", name="WR2", long_term=True)
        s.add_all([t1, t2])
        await s.commit()
        await s.refresh(t1)
        await s.refresh(t2)
        id1, id2 = t1.id, t2.id

    ts = datetime.now(UTC)
    n = await poller.write_readings([(id1, 1.5, 192), (id2, 2.5, 0)], ts, sessionmaker=sm)
    assert n == 2

    async with sm() as s:
        cnt = await s.scalar(
            select(func.count()).select_from(TagReading).where(TagReading.tag_id.in_([id1, id2]))
        )
    assert cnt == 2


@pytest.mark.asyncio
async def test_write_readings_conflict_returns_zero(db_engine):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(node_id="ns=2;s=WR3", name="WR3", long_term=True)
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    ts = datetime.now(UTC)
    assert await poller.write_readings([(tid, 1.0, 192)], ts, sessionmaker=sm) == 1
    # same (tag_id, timestamp) -> PK conflict -> whole batch rolled back
    assert await poller.write_readings([(tid, 9.0, 192)], ts, sessionmaker=sm) == 0


@pytest.mark.asyncio
async def test_write_readings_empty():
    assert await poller.write_readings([], datetime.now(UTC)) == 0


@pytest.mark.asyncio
async def test_read_plc_group_records_plc_read_metric(monkeypatch):
    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(1.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)
    before = _sample("scada_plc_read_seconds_count", {"plc": "10.9.9.9"})
    items = [(11, ReadSpec("DB", 1, 0, 0, 4, "REAL"))]
    await poller.read_plc_group(("10.9.9.9", 0, 1), items, timeout=5)
    assert _sample("scada_plc_read_seconds_count", {"plc": "10.9.9.9"}) - before == 1.0


@pytest.mark.asyncio
async def test_run_once_records_rows_and_bad_metrics(db_engine, monkeypatch):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        good = Tag(
            node_id="ns=2;s=MG",
            name="MG",
            long_term=True,
            plc_ip="10.0.0.6",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        bad = Tag(
            node_id="ns=2;s=MB",
            name="MB",
            long_term=True,
            plc_ip="10.0.0.7",
            s7_address="DB10,DD4",
            data_type="REAL",
            sample_interval=1,
        )
        s.add_all([good, bad])
        await s.commit()
        await s.refresh(good)
        await s.refresh(bad)
        bad_ip = bad.plc_ip

    async def fake_batch(ip, rack, slot, specs, name=""):
        if ip == bad_ip:
            return [(None, 0) for _ in specs]
        return [(42.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    rows_before = _sample("scada_rows_written_total")
    bad_before = _sample("scada_bad_quality_total")
    try:
        await poller.run_once({}, now=2000.0, sessionmaker=sm, timeout=5)

        assert _sample("scada_rows_written_total") - rows_before == 2.0
        assert _sample("scada_bad_quality_total") - bad_before == 1.0
    finally:
        # session-scoped engine -> bu tag'leri başka testlerden izole et
        from sqlalchemy import delete

        async with sm() as s:
            ids = [good.id, bad.id]
            await s.execute(delete(TagReading).where(TagReading.tag_id.in_(ids)))
            await s.execute(delete(Tag).where(Tag.id.in_(ids)))
            await s.commit()


@pytest.mark.asyncio
async def test_run_once_writes_db_and_cache(db_engine, monkeypatch):
    from app.collector.cache import latest_cache

    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=RT1",
            name="RT1",
            long_term=True,
            plc_ip="10.0.0.5",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(42.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    last_read: dict[int, float] = {}
    written, min_interval = await poller.run_once(last_read, now=1000.0, sessionmaker=sm, timeout=5)

    assert written == 1
    assert min_interval == 1
    assert last_read[tid] == 1000.0

    cr = latest_cache.get(tid)
    assert cr is not None and cr.value == 42.0 and cr.quality == 192

    async with sm() as s:
        cnt = await s.scalar(
            select(func.count()).select_from(TagReading).where(TagReading.tag_id == tid)
        )
    assert cnt == 1
