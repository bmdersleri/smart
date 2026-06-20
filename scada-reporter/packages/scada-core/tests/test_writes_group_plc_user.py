import httpx
from scada_core.client import AsyncScadaClient
from scada_core.catalog import CATALOG


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


async def test_group_update_omits_none_fields():
    seen = {}

    def handler(req):
        seen["body"] = req.read().decode()
        assert req.url.path == "/api/groups/3"
        return httpx.Response(200, json={"id": 3})

    c = _client(handler)
    r = await c.group_update(3, name="X")
    assert r.ok
    assert '"name"' in seen["body"] and '"parent_id"' not in seen["body"]
    await c.aclose()


async def test_group_assign_body():
    def handler(req):
        assert req.url.path == "/api/groups/3/assign"
        assert '"tag_ids"' in req.read().decode()
        return httpx.Response(200, json={"assigned": 2})

    c = _client(handler)
    assert (await c.group_assign(3, [1, 2])).ok
    await c.aclose()


async def test_plc_update_patch_path():
    def handler(req):
        assert req.method == "PATCH" and req.url.path == "/api/plc/PLC1"
        return httpx.Response(200, json={"name": "PLC1"})

    c = _client(handler)
    assert (await c.plc_update("PLC1", ip="10.0.0.1")).ok
    await c.aclose()


async def test_user_create_body():
    def handler(req):
        assert req.url.path == "/api/users/"
        body = req.read().decode()
        assert '"username"' in body and '"role"' in body
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    assert (await c.user_create("u1", "u1@x.com", "secret6")).ok
    await c.aclose()


async def test_user_delete_403():
    def handler(req):
        return httpx.Response(403, text="forbidden")

    c = _client(handler)
    r = await c.user_delete(2)
    assert r.ok is False and r.error["status"] == 403
    await c.aclose()


def test_catalog_tiers_group_plc_user():
    assert CATALOG["group_create"].tier == "write"
    assert CATALOG["plc_update"].tier == "write"
    assert CATALOG["group_delete"].tier == "destructive"
    assert CATALOG["plc_delete"].tier == "destructive"
    assert CATALOG["user_create"].tier == "destructive"
    assert CATALOG["user_delete"].tier == "destructive"
