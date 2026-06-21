from app.collector.plc_health_tracker import PlcHealthTracker

KEY = ("10.0.0.1", 0, 1)


def test_record_read_tallies_and_resets_on_snapshot():
    t = PlcHealthTracker()
    t.record_read(KEY, "PLC1", good=5, bad=1, now=100.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=100.0)
    obs = t.snapshot(now=100.0, flap_window=120.0)
    assert len(obs) == 1
    o = obs[0]
    assert o.key == KEY
    assert o.good_count == 5 and o.bad_count == 1
    assert o.connected is True
    # last success was now -> ~0 seconds since success
    assert o.seconds_since_success < 1.0
    # second snapshot: counters reset
    obs2 = t.snapshot(now=101.0, flap_window=120.0)
    assert obs2[0].good_count == 0 and obs2[0].bad_count == 0


def test_reconnect_transitions_counted_within_window():
    t = PlcHealthTracker()
    t.observe_connection(KEY, "PLC1", connected=False, now=0.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=1.0)  # reconnect #1
    t.observe_connection(KEY, "PLC1", connected=False, now=2.0)
    t.observe_connection(KEY, "PLC1", connected=True, now=3.0)  # reconnect #2
    obs = t.snapshot(now=4.0, flap_window=120.0)
    assert obs[0].reconnects_in_window == 2
    # outside window -> pruned
    obs_later = t.snapshot(now=200.0, flap_window=120.0)
    assert obs_later[0].reconnects_in_window == 0


def test_seconds_since_success_uses_first_seen_when_never_good():
    t = PlcHealthTracker()
    t.record_read(KEY, "PLC1", good=0, bad=3, now=10.0)
    obs = t.snapshot(now=80.0, flap_window=120.0)
    assert obs[0].seconds_since_success >= 70.0


def test_last_error_surfaces_then_clears_on_good_read():
    t = PlcHealthTracker()
    t.record_read(KEY, "PLC1", good=0, bad=3, now=1.0, error="Receive timeout")
    obs = t.snapshot(now=2.0, flap_window=120.0)
    assert obs[0].last_error == "Receive timeout"
    # başarılı okuma hatayı temizler
    t.record_read(KEY, "PLC1", good=5, bad=0, now=3.0)
    obs2 = t.snapshot(now=4.0, flap_window=120.0)
    assert obs2[0].last_error is None
