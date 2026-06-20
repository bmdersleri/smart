import httpx
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_list_tags_ok():
    def handler(req):
        assert req.url.path == "/api/tags/"
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    c = _client(handler)
    r = await c.list_tags()
    assert r.ok and r.data[0]["name"] == "PT-101"
    await c.aclose()


async def test_run_sql_posts_to_query_run_with_sql_field():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(200, json={"rows": []})

    c = _client(handler)
    r = await c.run_sql("SELECT 1")
    assert r.ok
    assert seen["path"] == "/api/query/run"
    assert '"sql"' in seen["body"]  # FIX: alan adı "query" değil "sql"
    await c.aclose()


async def test_http_error_becomes_result():
    def handler(req):
        return httpx.Response(403, json={"detail": "forbidden"})

    c = _client(handler)
    r = await c.list_plcs()
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


async def test_login_sets_token():
    def handler(req):
        if req.url.path == "/api/auth/token":
            return httpx.Response(200, json={"access_token": "TK"})
        assert req.headers["Authorization"] == "Bearer TK"
        return httpx.Response(200, json=[])

    c = _client(handler)
    await c.login("admin", "x")
    r = await c.list_tags()
    assert r.ok
    await c.aclose()
