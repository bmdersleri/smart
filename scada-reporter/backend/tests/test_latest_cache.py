"""Son-değer önbelleği testleri."""

from datetime import UTC, datetime

from app.collector.cache import CachedReading, LatestValueCache


def test_cache_update_and_get():
    c = LatestValueCache()
    ts = datetime.now(UTC)
    c.update(1, 3.5, 192, ts)
    r = c.get(1)
    assert isinstance(r, CachedReading)
    assert (r.value, r.quality, r.timestamp) == (3.5, 192, ts)
    assert c.get(999) is None


def test_cache_update_many_and_get_many():
    c = LatestValueCache()
    ts = datetime.now(UTC)
    c.update_many([(1, 1.0, 192), (2, None, 0)], ts)
    got = c.get_many([1, 2, 3])
    assert set(got) == {1, 2}
    assert got[1].value == 1.0
    assert got[2].value is None and got[2].quality == 0


def test_cache_snapshot_is_independent_copy():
    c = LatestValueCache()
    ts = datetime.now(UTC)
    c.update(1, 1.0, 192, ts)
    snap = c.snapshot()
    c.update(2, 2.0, 192, ts)
    assert set(snap) == {1}  # snapshot unaffected by later writes
