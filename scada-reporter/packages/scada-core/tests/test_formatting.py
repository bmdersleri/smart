import json
from scada_core.envelope import ok, fail
from scada_core.formatting import to_json, to_text


def test_to_json_success():
    s = to_json(ok({"a": 1}))
    assert json.loads(s) == {"ok": True, "data": {"a": 1}, "error": None}


def test_to_json_error():
    s = to_json(fail("http", "no", status=500))
    parsed = json.loads(s)
    assert parsed["ok"] is False and parsed["error"]["status"] == 500


def test_to_text_is_json_not_repr():
    s = to_text({"name": "PT-101"})
    assert s == '{"name": "PT-101"}'  # str()/repr değil, geçerli JSON
