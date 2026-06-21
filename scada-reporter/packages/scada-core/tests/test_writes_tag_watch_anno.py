import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_watchlist_add_posts_to_item_path():
    def handler(req):
        assert req.method == "POST" and req.url.path == "/api/dashboard/watchlist/5"
        return httpx.Response(201, json={"ok": True})

    c = _client(handler)
    assert (await c.watchlist_add(5)).ok
    await c.aclose()


async def test_watchlist_remove_deletes():
    def handler(req):
        assert req.method == "DELETE" and req.url.path == "/api/dashboard/watchlist/5"
        return httpx.Response(204)

    c = _client(handler)
    assert (await c.watchlist_remove(5)).ok
    await c.aclose()


async def test_annotation_add_body():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    r = await c.annotation_add(ts="2026-06-20T00:00:00Z", text="note", tag_id=3)
    assert r.ok and seen["path"] == "/api/annotations/"
    assert '"text"' in seen["body"] and '"tag_id"' in seen["body"]
    await c.aclose()


async def test_annotation_delete_403_becomes_result():
    def handler(req):
        return httpx.Response(403, json={"detail": "forbidden"})

    c = _client(handler)
    r = await c.annotation_delete(9)
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


def test_catalog_tiers_for_tag_watch_anno():
    assert CATALOG["watchlist_add"].tier == "write"
    assert CATALOG["annotation_delete"].tier == "write"
    assert CATALOG["delete_tag"].tier == "destructive"
    assert CATALOG["update_tag"].tier == "write"
