import httpx
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_update_tag_builds_payload_from_non_none_fields():
    seen = {}

    def handler(req):
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(200, json={"id": 5, "unit": "bar"})

    c = _client(handler)
    r = await c.update_tag(5, unit="bar", max_alarm=10.0)
    assert r.ok
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/api/tags/5"
    assert '"unit"' in seen["body"] and '"max_alarm"' in seen["body"]
    assert '"device"' not in seen["body"]  # None fields excluded
    await c.aclose()


async def test_update_tag_empty_payload_raises():
    c = _client(lambda req: httpx.Response(200, json={}))
    import pytest

    with pytest.raises(ValueError):
        await c.update_tag(5)
    await c.aclose()


async def test_update_tag_error_becomes_result():
    def handler(req):
        return httpx.Response(404, text="Tag bulunamadi")

    c = _client(handler)
    r = await c.update_tag(5, unit="x")
    assert r.ok is False and r.error["status"] == 404
    await c.aclose()


async def test_delete_tag_returns_deleted_marker():
    def handler(req):
        assert req.method == "DELETE" and req.url.path == "/api/tags/9"
        return httpx.Response(204)

    c = _client(handler)
    r = await c.delete_tag(9)
    assert r.ok and r.data == {"deleted": True, "tag_id": 9}
    await c.aclose()


async def test_list_report_history_path_and_data():
    def handler(req):
        assert req.url.path == "/api/reports/history"
        return httpx.Response(200, json=[{"id": 1, "name": "r1"}])

    c = _client(handler)
    r = await c.list_report_history()
    assert r.ok and r.data[0]["name"] == "r1"
    await c.aclose()


async def test_list_report_history_error():
    def handler(req):
        return httpx.Response(401, text="Unauthorized")

    c = _client(handler)
    r = await c.list_report_history()
    assert r.ok is False and r.error["status"] == 401
    await c.aclose()


async def test_download_report_history_parses_content_disposition():
    def handler(req):
        assert req.url.path == "/api/reports/history/3/download"
        return httpx.Response(
            200,
            content=b"PK\x03\x04",
            headers={"content-disposition": 'attachment; filename="rapor.xlsx"'},
        )

    c = _client(handler)
    r = await c.download_report_history(3)
    assert r.ok
    assert r.data["filename"] == "rapor.xlsx"
    assert r.data["content"] == b"PK\x03\x04"
    await c.aclose()


async def test_download_report_history_default_filename_when_no_header():
    def handler(req):
        return httpx.Response(200, content=b"data", headers={})

    c = _client(handler)
    r = await c.download_report_history(7)
    assert r.ok and r.data["filename"] == "scada_rapor_7.bin"
    await c.aclose()


async def test_overview_and_explore_paths():
    def handler(req):
        return httpx.Response(200, json={"path": req.url.path})

    c = _client(handler)
    assert (await c.overview()).data["path"] == "/api/dashboard/overview"
    assert (await c.explore_schema()).data["path"] == "/api/explore/schema"
    assert (await c.explore_summary()).data["path"] == "/api/explore/summary"
    await c.aclose()


async def test_trend_by_ids_params():
    def handler(req):
        assert req.url.path == "/api/dashboard/trend"
        assert "tag_ids=1" in str(req.url) and "hours=48" in str(req.url)
        return httpx.Response(200, json=[])

    c = _client(handler)
    r = await c.trend([1, 2], hours=48)
    assert r.ok
    await c.aclose()
