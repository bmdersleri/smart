"""Tests for collector disconnect/timeout and bad-quality storage paths.

Covers the error path in poller.read_plc_group() when the PLC read raises
asyncio.TimeoutError (via asyncio.wait_for) or a generic connection error,
asserting that the entire batch is marked BAD quality and that
metrics.add_bad_quality() is incremented accordingly.

Also covers run_once() end-to-end with a failing PLC:
- all rows produced are BAD quality
- bad_quality counter increases
- readings are stored to DB with quality=0 (BAD)
"""

import asyncio

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collector import poller
from app.collector.s7_collector import BAD, GOOD, ReadSpec
from app.models.tag import Tag, TagReading


def _sample(name: str, labels: dict | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


# ── read_plc_group error paths ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_plc_group_asyncio_timeout_marks_all_bad(monkeypatch):
    """asyncio.TimeoutError inside wait_for → every row gets BAD quality."""

    async def slow_batch(ip, rack, slot, specs, name=""):
        await asyncio.sleep(10)  # will be cut off by the timeout arg

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", slow_batch)

    items = [
        (1, ReadSpec("DB", 1, 0, 0, 4, "REAL")),
        (2, ReadSpec("DB", 1, 4, 0, 4, "REAL")),
        (3, ReadSpec("DB", 1, 8, 0, 4, "REAL")),
    ]
    rows = await poller.read_plc_group(("10.1.1.1", 0, 1), items, timeout=0.05)

    assert len(rows) == 3
    for _tag_id, value, quality in rows:
        assert quality == BAD
        assert value is None


@pytest.mark.asyncio
async def test_read_plc_group_connection_error_marks_all_bad(monkeypatch):
    """A generic OSError (disconnect) → every row gets BAD quality."""

    async def failing_batch(ip, rack, slot, specs, name=""):
        raise OSError("Connection refused")

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", failing_batch)

    items = [
        (10, ReadSpec("DB", 2, 0, 0, 4, "REAL")),
        (11, ReadSpec("DB", 2, 4, 0, 4, "REAL")),
    ]
    rows = await poller.read_plc_group(("10.2.2.2", 0, 1), items, timeout=5)

    assert len(rows) == 2
    for _tag_id, value, quality in rows:
        assert quality == BAD
        assert value is None


# ── run_once end-to-end with failing PLC ────────────────────────────────────


@pytest.mark.asyncio
async def test_run_once_with_plc_timeout_stores_bad_quality(db_engine, monkeypatch):
    """run_once with a timing-out PLC stores BAD-quality readings and increments
    the bad_quality Prometheus counter."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)

    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=CF_TIMEOUT",
            name="CF_TIMEOUT",
            long_term=True,
            plc_ip="10.99.99.1",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def slow_batch(ip, rack, slot, specs, name=""):
        await asyncio.sleep(10)

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", slow_batch)

    bad_before = _sample("scada_bad_quality_total")
    written, _ = await poller.run_once({}, now=5000.0, sessionmaker=sm, timeout=0.05)

    # One BAD-quality row should have been written to DB
    assert written == 1

    # bad_quality counter must have gone up by 1
    assert _sample("scada_bad_quality_total") - bad_before == 1.0

    # Verify DB row has quality == BAD (0)
    async with sm() as s:
        result = await s.execute(select(TagReading).where(TagReading.tag_id == tid))
        readings = result.scalars().all()
    assert len(readings) == 1
    assert readings[0].quality == BAD
    assert readings[0].value is None


@pytest.mark.asyncio
async def test_run_once_with_plc_error_stores_bad_quality(db_engine, monkeypatch):
    """run_once where PLC raises an error (not timeout) also stores BAD readings."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)

    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=CF_ERROR",
            name="CF_ERROR",
            long_term=True,
            plc_ip="10.99.99.2",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def error_batch(ip, rack, slot, specs, name=""):
        raise RuntimeError("PLC disconnected")

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", error_batch)

    bad_before = _sample("scada_bad_quality_total")
    written, _ = await poller.run_once({}, now=6000.0, sessionmaker=sm, timeout=5)

    assert written == 1
    assert _sample("scada_bad_quality_total") - bad_before >= 1.0

    async with sm() as s:
        result = await s.execute(select(TagReading).where(TagReading.tag_id == tid))
        readings = result.scalars().all()
    assert len(readings) == 1
    assert readings[0].quality == BAD


# ── bad-quality storage distinct from good-quality ──────────────────────────


@pytest.mark.asyncio
async def test_bad_quality_reading_stored_with_correct_quality_value(db_engine, monkeypatch):
    """A BAD-quality reading is stored in DB with quality=0, distinct from GOOD=192."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)

    async with sm() as s:
        t_good = Tag(
            node_id="ns=2;s=BQ_GOOD",
            name="BQ_GOOD",
            long_term=True,
            plc_ip="10.88.88.1",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        t_bad = Tag(
            node_id="ns=2;s=BQ_BAD",
            name="BQ_BAD",
            long_term=True,
            plc_ip="10.88.88.2",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add_all([t_good, t_bad])
        await s.commit()
        await s.refresh(t_good)
        await s.refresh(t_bad)
        good_id = t_good.id
        bad_id = t_bad.id

    async def mixed_batch(ip, rack, slot, specs, name=""):
        if ip == "10.88.88.1":
            return [(42.0, GOOD) for _ in specs]
        else:
            return [(None, BAD) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", mixed_batch)

    written, _ = await poller.run_once({}, now=7000.0, sessionmaker=sm, timeout=5)
    assert written == 2

    async with sm() as s:
        result = await s.execute(select(TagReading).where(TagReading.tag_id.in_([good_id, bad_id])))
        readings = {r.tag_id: r for r in result.scalars().all()}

    assert readings[good_id].quality == GOOD
    assert readings[good_id].value == 42.0
    assert readings[bad_id].quality == BAD
    assert readings[bad_id].value is None
