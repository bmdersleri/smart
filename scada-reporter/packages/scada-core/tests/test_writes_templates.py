import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_template_create_posts_payload():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    r = await c.template_create({"name": "T1", "tag_ids": [1, 2]})
    assert r.ok and seen["path"] == "/api/advanced-reports/templates"
    assert '"name"' in seen["body"]
    await c.aclose()


async def test_template_run_path_and_body():
    def handler(req):
        assert req.url.path == "/api/advanced-reports/templates/7/run"
        assert '"start"' in req.read().decode()
        return httpx.Response(202, json={"archive_id": 3})

    c = _client(handler)
    assert (await c.template_run(7, start="2026-06-01T00:00:00Z")).ok
    await c.aclose()


async def test_scheduled_toggle_patch():
    def handler(req):
        assert req.method == "PATCH"
        assert req.url.path == "/api/advanced-reports/scheduled/4/toggle"
        return httpx.Response(200, json={"enabled": False})

    c = _client(handler)
    assert (await c.scheduled_toggle(4)).ok
    await c.aclose()


async def test_template_delete_204():
    def handler(req):
        assert req.method == "DELETE"
        assert req.url.path == "/api/advanced-reports/templates/9"
        return httpx.Response(204)

    c = _client(handler)
    assert (await c.template_delete(9)).ok
    await c.aclose()


def test_catalog_tiers_for_templates():
    assert CATALOG["template_create"].tier == "write"
    assert CATALOG["template_run"].tier == "write"
    assert CATALOG["scheduled_toggle"].tier == "write"
    assert CATALOG["template_delete"].tier == "destructive"
    assert CATALOG["scheduled_delete"].tier == "destructive"
    assert CATALOG["archive_delete"].tier == "destructive"
