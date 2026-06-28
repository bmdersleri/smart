from app.services import backup_progress as bp


def test_progress_lifecycle():
    key = "job-test-1"
    bp.clear(key)
    assert bp.get(key) is None

    bp.start(key)
    p = bp.get(key)
    assert p is not None and p["status"] == "running" and p["percent"] == 0.0

    bp.update(key, phase="compress", fraction=0.5)
    p = bp.get(key)
    assert p["phase"] == "compress" and p["percent"] == 50.0

    bp.finish(key)
    p = bp.get(key)
    assert p["status"] == "done" and p["percent"] == 100.0
    bp.clear(key)


def test_progress_clamps_and_records_error():
    key = "job-test-2"
    bp.start(key)
    bp.update(key, phase="compress", fraction=5.0)  # >1 clamps to 100
    assert bp.get(key)["percent"] == 100.0
    bp.update(key, phase="compress", fraction=-1.0)  # <0 clamps to 0
    assert bp.get(key)["percent"] == 0.0

    bp.finish(key, error="boom")
    p = bp.get(key)
    assert p["status"] == "failed" and p["error"] == "boom"
    bp.clear(key)


def test_update_unknown_key_is_noop():
    bp.clear("missing")
    bp.update("missing", phase="x", fraction=0.5)  # must not raise
    assert bp.get("missing") is None
