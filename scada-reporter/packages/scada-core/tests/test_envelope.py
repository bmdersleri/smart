import httpx
from scada_core.envelope import ok, fail, from_http_error


def test_ok_wraps_data():
    r = ok({"a": 1})
    assert r.ok is True
    assert r.data == {"a": 1}
    assert r.error is None


def test_fail_sets_error():
    r = fail("connection", "refused")
    assert r.ok is False
    assert r.error == {"kind": "connection", "detail": "refused", "status": None}


def test_from_http_error_json_detail():
    resp = httpx.Response(400, json={"detail": "bad"})
    r = from_http_error(resp)
    assert r.ok is False
    assert r.error["status"] == 400
    assert r.error["detail"] == {"detail": "bad"}


def test_legacy_success_returns_data():
    assert ok([1, 2]).legacy() == [1, 2]


def test_legacy_error_shape_matches_old_cli():
    r = fail("http", "nope", status=404)
    assert r.legacy() == {"error": True, "status": 404, "detail": "nope"}
