# tests/test_plc_detector.py
from app.monitor.detector import (
    DetectorConfig,
    PlcMonitorState,
    PlcObservation,
    evaluate,
)

CFG = DetectorConfig(
    stale_seconds=60.0,
    partial_bad_ratio=0.5,
    partial_bad_cycles=3,
    flap_count=3,
    recover_cycles=2,
)
KEY = ("10.0.0.1", 0, 1)


def _obs(connected=True, good=10, bad=0, sss=0.0, reconnects=0):
    return PlcObservation(
        key=KEY,
        name="PLC1",
        connected=connected,
        good_count=good,
        bad_count=bad,
        seconds_since_success=sss,
        reconnects_in_window=reconnects,
    )


def _fresh():
    return PlcMonitorState(open={})


def test_disconnect_needs_two_cycles():
    s = _fresh()
    r1 = evaluate(s, _obs(connected=False, good=0, bad=0), CFG, now=1.0)
    assert r1.opened == []  # 1. tick: henüz açma
    r2 = evaluate(r1.state, _obs(connected=False, good=0, bad=0), CFG, now=2.0)
    assert [i.kind for i in r2.opened] == ["disconnected"]
    assert r2.opened[0].severity == "critical"
    assert "disconnected" in r2.state.open


def test_disconnect_resolves_after_recover_cycles():
    s = _fresh()
    s = evaluate(s, _obs(connected=False), CFG, now=1.0).state
    r = evaluate(s, _obs(connected=False), CFG, now=2.0)  # opened
    s = r.state
    s = evaluate(s, _obs(connected=True), CFG, now=3.0).state  # clean 1
    r2 = evaluate(s, _obs(connected=True), CFG, now=4.0)  # clean 2 -> resolve
    assert r2.resolved == ["disconnected"]
    assert "disconnected" not in r2.state.open


def test_stale_data_when_connected_no_good_reads():
    s = _fresh()
    r = evaluate(s, _obs(connected=True, good=0, bad=0, sss=65.0), CFG, now=10.0)
    assert [i.kind for i in r.opened] == ["stale_data"]
    assert r.opened[0].severity == "critical"


def test_partial_bad_requires_consecutive_cycles():
    s = _fresh()
    obs = _obs(connected=True, good=2, bad=8, sss=0.0)  # bad ratio 0.8 > 0.5
    s = evaluate(s, obs, CFG, now=1.0).state  # streak 1
    s = evaluate(s, obs, CFG, now=2.0).state  # streak 2
    r = evaluate(s, obs, CFG, now=3.0)  # streak 3 -> open
    assert [i.kind for i in r.opened] == ["partial_bad"]
    assert r.opened[0].severity == "warning"


def test_flapping_when_reconnects_exceed_count():
    s = _fresh()
    r = evaluate(s, _obs(connected=True, reconnects=3), CFG, now=1.0)
    assert [i.kind for i in r.opened] == ["flapping"]


def test_no_duplicate_open_for_same_kind():
    s = _fresh()
    s = evaluate(s, _obs(connected=False), CFG, now=1.0).state
    r = evaluate(s, _obs(connected=False), CFG, now=2.0)  # opens
    s = r.state
    r2 = evaluate(s, _obs(connected=False), CFG, now=3.0)  # still down
    assert r2.opened == []  # no second incident
    assert "disconnected" in r2.state.open


def test_hysteresis_reset_on_reactivation():
    s = _fresh()
    # open the incident (two disconnected cycles)
    s = evaluate(s, _obs(connected=False), CFG, now=1.0).state
    s = evaluate(s, _obs(connected=False), CFG, now=2.0).state  # opened
    # one clean cycle -> clean_cycles = 1
    s = evaluate(s, _obs(connected=True), CFG, now=3.0).state
    # condition reactivates (needs two disconnects to reach streak=2)
    s = evaluate(s, _obs(connected=False), CFG, now=4.0).state
    s = evaluate(
        s, _obs(connected=False), CFG, now=5.0
    ).state  # streak=2 -> reactivated, clean_cycles reset to 0
    # now needs two full clean cycles again, not one
    s = evaluate(s, _obs(connected=True), CFG, now=6.0).state  # clean_cycles = 1
    r = evaluate(s, _obs(connected=True), CFG, now=7.0)  # clean_cycles = 2 -> resolved
    assert r.resolved == ["disconnected"]
