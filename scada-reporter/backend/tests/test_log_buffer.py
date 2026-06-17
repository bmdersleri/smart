"""In-memory ring log buffer + handler."""

import logging

from app.core.log_buffer import RingLogHandler


def _rec(handler: RingLogHandler, level: int, msg: str, name: str = "test") -> None:
    handler.emit(logging.LogRecord(name, level, __file__, 1, msg, None, None))


def test_emit_captures_record_fields():
    h = RingLogHandler(maxlen=10)
    _rec(h, logging.INFO, "hello world", name="app.poller")
    snap = h.snapshot()
    assert len(snap) == 1
    r = snap[0]
    assert r["seq"] == 1
    assert r["level"] == "INFO"
    assert r["levelno"] == logging.INFO
    assert r["name"] == "app.poller"
    assert r["msg"] == "hello world"
    assert "T" in r["ts"]  # ISO timestamp


def test_seq_is_monotonic():
    h = RingLogHandler(maxlen=10)
    for i in range(5):
        _rec(h, logging.INFO, f"m{i}")
    seqs = [r["seq"] for r in h.snapshot()]
    assert seqs == [1, 2, 3, 4, 5]


def test_ring_caps_at_maxlen_and_drops_oldest():
    h = RingLogHandler(maxlen=3)
    for i in range(5):
        _rec(h, logging.INFO, f"m{i}")
    snap = h.snapshot()
    assert len(snap) == 3
    assert [r["msg"] for r in snap] == ["m2", "m3", "m4"]
    assert [r["seq"] for r in snap] == [3, 4, 5]


def test_snapshot_after_seq_filters_seen():
    h = RingLogHandler(maxlen=10)
    for i in range(4):
        _rec(h, logging.INFO, f"m{i}")
    snap = h.snapshot(after_seq=2)
    assert [r["seq"] for r in snap] == [3, 4]


def test_snapshot_min_level_filters_lower():
    h = RingLogHandler(maxlen=10)
    _rec(h, logging.INFO, "info-line")
    _rec(h, logging.WARNING, "warn-line")
    _rec(h, logging.ERROR, "err-line")
    msgs = [r["msg"] for r in h.snapshot(min_level=logging.WARNING)]
    assert msgs == ["warn-line", "err-line"]


def test_emit_never_raises_on_bad_record():
    h = RingLogHandler(maxlen=10)
    bad = logging.LogRecord("x", logging.INFO, __file__, 1, "%d", ("not-int",), None)
    h.emit(bad)  # must not raise
    assert len(h.snapshot()) == 1
