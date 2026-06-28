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
async def test_write_readings_sqlite_uses_insert_not_copy(db_engine, monkeypatch):
    """SQLite asla COPY yoluna girmez (dialect guard); INSERT ile yazar."""

    async def _boom(*a, **k):
        raise AssertionError("_copy_readings must not run on sqlite")

    monkeypatch.setattr(poller, "_copy_readings", _boom)
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(node_id="ns=2;s=WR_SL", name="WRSL", long_term=True)
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id
    n = await poller.write_readings([(tid, 1.0, 192)], datetime.now(UTC), sessionmaker=sm)
    assert n == 1


class _FakePgSession:
    def __init__(self) -> None:
        self.bind = type("B", (), {"dialect": type("D", (), {"name": "postgresql"})()})()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_write_readings_routes_to_copy_on_postgresql(monkeypatch):
    """PG + flag açık → _copy_readings'e yönlenir."""
    monkeypatch.setattr(settings, "S7_PG_COPY_INGEST", True)

    async def _fake_copy(db, rows, ts):
        return 7

    monkeypatch.setattr(poller, "_copy_readings", _fake_copy)
    n = await poller.write_readings([(1, 1.0, 192)], datetime.now(UTC), sessionmaker=_FakePgSession)
    assert n == 7


@pytest.mark.asyncio
async def test_write_readings_flag_off_uses_insert_on_postgresql(monkeypatch):
    """Kill-switch: flag kapalı → PG'de bile INSERT (COPY çağrılmaz)."""
    monkeypatch.setattr(settings, "S7_PG_COPY_INGEST", False)

    async def _boom(*a, **k):
        raise AssertionError("_copy_readings must not run when flag off")

    async def _fake_insert(db, rows, ts):
        return 3

    monkeypatch.setattr(poller, "_copy_readings", _boom)
    monkeypatch.setattr(poller, "_insert_readings", _fake_insert)
    n = await poller.write_readings([(1, 1.0, 192)], datetime.now(UTC), sessionmaker=_FakePgSession)
    assert n == 3


def test_write_buffer_add_and_drain():
    ts = datetime.now(UTC)
    buf = poller.WriteBuffer(maxlen=5)
    buf.add(ts, [(1, 1.0, 192)])
    buf.add(ts, [(2, 2.0, 192)])
    assert len(buf) == 2
    drained = buf.drain()
    assert len(drained) == 2
    assert len(buf) == 0  # drain temizler


def test_write_buffer_bounded_drops_oldest():
    ts = datetime.now(UTC)
    buf = poller.WriteBuffer(maxlen=2)
    buf.add(ts, [(1, 1.0, 192)])
    buf.add(ts, [(2, 2.0, 192)])
    buf.add(ts, [(3, 3.0, 192)])  # taşar -> en eski düşer
    drained = buf.drain()
    assert [r[0][0] for _, r in drained] == [2, 3]


@pytest.mark.asyncio
async def test_run_once_buffers_on_db_failure_then_flushes(db_engine, monkeypatch):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=BUF",
            name="BUF",
            long_term=True,
            plc_ip="10.0.0.9",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(7.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    calls = {"n": 0}
    real_write = poller.write_readings

    async def flaky_write(rows, ts, sessionmaker=sm):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("DB down")  # ilk tick: transient hata
        return await real_write(rows, ts, sessionmaker=sm)

    buf = poller.WriteBuffer()
    monkeypatch.setattr(poller, "write_readings", flaky_write)
    try:
        w1, _ = await poller.run_once({}, now=1.0, sessionmaker=sm, timeout=5, buffer=buf)
        assert w1 == 0
        assert len(buf) == 1
        w2, _ = await poller.run_once({}, now=2.0, sessionmaker=sm, timeout=5, buffer=buf)
        assert w2 >= 1
        assert len(buf) == 0
    finally:
        from sqlalchemy import delete

        monkeypatch.setattr(poller, "write_readings", real_write)
        async with sm() as s:
            await s.execute(delete(TagReading).where(TagReading.tag_id == tid))
            await s.execute(delete(Tag).where(Tag.id == tid))
            await s.commit()


def test_should_store_first_reading_always_stores():
    assert poller.should_store(1, 5.0, 192, now=0.0, last_stored={}, deadband=1.0, heartbeat=300)


def test_should_store_no_deadband_always_stores():
    ls = {1: (5.0, 192, 0.0)}
    assert poller.should_store(1, 5.0, 192, now=1.0, last_stored=ls, deadband=None, heartbeat=300)


def test_should_store_within_deadband_skips():
    ls = {1: (5.0, 192, 0.0)}
    assert not poller.should_store(
        1, 5.4, 192, now=1.0, last_stored=ls, deadband=1.0, heartbeat=300
    )


def test_should_store_beyond_deadband_stores():
    ls = {1: (5.0, 192, 0.0)}
    assert poller.should_store(1, 6.5, 192, now=1.0, last_stored=ls, deadband=1.0, heartbeat=300)


def test_should_store_quality_change_stores():
    ls = {1: (5.0, 192, 0.0)}
    assert poller.should_store(1, 5.0, 0, now=1.0, last_stored=ls, deadband=1.0, heartbeat=300)


def test_should_store_heartbeat_elapsed_stores():
    ls = {1: (5.0, 192, 0.0)}
    assert poller.should_store(1, 5.0, 192, now=301.0, last_stored=ls, deadband=1.0, heartbeat=300)


@pytest.mark.asyncio
async def test_run_once_deadband_skips_unchanged(db_engine, monkeypatch):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=DBN1",
            name="DBN1",
            long_term=True,
            plc_ip="10.0.0.8",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
            deadband=1.0,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(42.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    last_read: dict[int, float] = {}
    last_stored: dict = {}
    try:
        w1, _ = await poller.run_once(
            last_read, now=1.0, sessionmaker=sm, timeout=5, last_stored=last_stored
        )
        w2, _ = await poller.run_once(
            last_read, now=2.0, sessionmaker=sm, timeout=5, last_stored=last_stored
        )
        assert w1 == 1  # ilk okuma yazılır
        assert w2 == 0  # deadband içinde -> atlanır

        async with sm() as s:
            cnt = await s.scalar(
                select(func.count()).select_from(TagReading).where(TagReading.tag_id == tid)
            )
        assert cnt == 1
    finally:
        from sqlalchemy import delete

        async with sm() as s:
            await s.execute(delete(TagReading).where(TagReading.tag_id == tid))
            await s.execute(delete(Tag).where(Tag.id == tid))
            await s.commit()


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


@pytest.mark.asyncio
async def test_run_once_reuses_tag_cache_within_ttl(db_engine, monkeypatch):
    """cache verilince tag listesi TTL boyunca yeniden kullanılır (DB'ye dönmez)."""
    from sqlalchemy import delete

    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sm() as s:
        t = Tag(
            node_id="ns=2;s=TC1",
            name="TC1",
            long_term=True,
            plc_ip="10.0.0.21",
            s7_address="DB10,DD0",
            data_type="REAL",
            sample_interval=1,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        tid = t.id

    async def fake_batch(ip, rack, slot, specs, name=""):
        return [(5.0, 192) for _ in specs]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    cache = poller.TagCache(ttl=10.0)
    last_read: dict[int, float] = {}
    try:
        # 1) ilk tick: DB'den çeker, okur, yazar
        w1, _ = await poller.run_once(last_read, now=100.0, sessionmaker=sm, timeout=5, cache=cache)
        # tag'i DB'den sil — cache hâlâ TTL içinde olduğundan görmemeli
        async with sm() as s:
            await s.execute(delete(Tag).where(Tag.id == tid))
            await s.commit()
        # 2) TTL içinde tick: cache'ten okur → tag silinmiş olsa da yazar
        w2, _ = await poller.run_once(last_read, now=105.0, sessionmaker=sm, timeout=5, cache=cache)
        # 3) TTL aşıldı: yeniden çeker → tag yok → ilgili yazma yok
        w3, _ = await poller.run_once(last_read, now=120.0, sessionmaker=sm, timeout=5, cache=cache)

        assert w1 == 1  # ilk okuma
        assert w2 == 1  # cache sayesinde silinen tag hâlâ okunur
        assert w3 == 0  # TTL sonrası refetch → tag gitmiş
    finally:
        async with sm() as s:
            await s.execute(delete(TagReading).where(TagReading.tag_id == tid))
            await s.execute(delete(Tag).where(Tag.id == tid))
            await s.commit()
