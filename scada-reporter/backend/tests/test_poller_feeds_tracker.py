import pytest

from app.collector import poller
from app.collector.plc_health_tracker import PlcHealthTracker
from app.collector.s7_collector import BAD, GOOD


@pytest.mark.asyncio
async def test_read_plc_group_records_good_bad(monkeypatch):
    tracker = PlcHealthTracker()
    monkeypatch.setattr(poller, "health_tracker", tracker)

    async def fake_batch(ip, rack, slot, specs):
        return [(1.0, GOOD), (None, BAD), (2.0, GOOD)]

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", fake_batch)

    key = ("10.0.0.9", 0, 1)
    # items: (tag_id, spec) — spec opaque burada
    items = [(1, object()), (2, object()), (3, object())]
    await poller.read_plc_group(key, items, timeout=5.0)

    obs = tracker.snapshot(now=1.0, flap_window=120.0)
    assert len(obs) == 1
    assert obs[0].good_count == 2
    assert obs[0].bad_count == 1


@pytest.mark.asyncio
async def test_read_plc_group_records_error_on_failure(monkeypatch):
    tracker = PlcHealthTracker()
    monkeypatch.setattr(poller, "health_tracker", tracker)

    async def boom(ip, rack, slot, specs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(poller.plc_manager, "read_plc_batch", boom)

    key = ("10.0.0.9", 0, 1)
    items = [(1, object())]
    await poller.read_plc_group(key, items, timeout=5.0)

    obs = tracker.snapshot(now=1.0, flap_window=120.0)
    assert obs[0].bad_count == 1
    assert obs[0].good_count == 0
    assert obs[0].last_error == "connection refused"
