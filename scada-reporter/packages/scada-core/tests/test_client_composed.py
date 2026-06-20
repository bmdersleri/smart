import httpx
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_query_trend_resolves_then_calls_range():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/api/ai/resolve":
            return httpx.Response(200, json={"tag_ids": [7], "matched": 1})
        if req.url.path == "/api/dashboard/trend_range":
            assert "tag_ids=7" in str(req.url)
            assert "start=" in str(req.url) and "end=" in str(req.url)
            return httpx.Response(200, json=[{"tag_id": 7, "series": []}])
        return httpx.Response(404)

    c = _client(handler)
    r = await c.query_trend(["debi"], "2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z")
    assert r.ok
    assert "/api/ai/resolve" in calls and "/api/dashboard/trend_range" in calls
    await c.aclose()


async def test_current_values_filters_by_name():
    def handler(req):
        assert req.url.path == "/api/dashboard/tags"
        return httpx.Response(
            200, json={"items": [{"name": "PT-101", "value": 1}, {"name": "FT-201", "value": 2}]}
        )

    c = _client(handler)
    r = await c.current_values(["PT-101"])
    assert r.ok
    names = [row["name"] for row in r.data]
    assert names == ["PT-101"]
    await c.aclose()


async def test_system_health_composes_three_calls():
    def handler(req):
        if req.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if req.url.path == "/api/plc/":
            return httpx.Response(200, json=[{"id": 1}, {"id": 2}])
        if req.url.path == "/api/tags/":
            return httpx.Response(200, json=[{"id": 1}, {"id": 2}, {"id": 3}])
        return httpx.Response(404)

    c = _client(handler)
    r = await c.system_health()
    assert r.ok
    assert r.data["plc_count"] == 2
    assert r.data["tag_count"] == 3
    await c.aclose()
