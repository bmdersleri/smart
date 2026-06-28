import httpx
from scada_core import endpoints as ep
from scada_core.catalog import CATALOG
from scada_core.client import AsyncScadaClient


def _client(handler):
    return AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))


def test_compliance_endpoint_constants():
    assert ep.COMPLIANCE_OVERVIEW == "/api/compliance/overview"
    assert ep.COMPLIANCE_EVENTS == "/api/compliance/events"
    assert ep.COMPLIANCE_EVALUATE == "/api/compliance/evaluate"


def test_compliance_capabilities_exist_with_correct_tiers():
    assert CATALOG["compliance_overview"].tier == "read"
    assert CATALOG["compliance_list_events"].tier == "read"
    assert CATALOG["compliance_evaluate"].tier == "write"


async def test_compliance_overview_path():
    def handler(req):
        return httpx.Response(200, json={"path": req.url.path, "method": req.method})

    c = _client(handler)
    r = await c.compliance_overview()
    assert r.ok
    assert r.data["path"] == "/api/compliance/overview"
    assert r.data["method"] == "GET"
    await c.aclose()


async def test_compliance_events_filters_become_query_params():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["query"] = str(
            req.url.query.decode() if isinstance(req.url.query, bytes) else req.url.query
        )
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"total": 0, "items": []})

    c = _client(handler)
    r = await c.compliance_events(
        permit_id=3, start="2026-05-01T00:00:00", end="2026-06-01T00:00:00", status="open"
    )
    assert r.ok
    assert seen["path"] == "/api/compliance/events"
    assert "permit_id=3" in seen["url"]
    assert "status=open" in seen["url"]
    assert "start=2026-05-01" in seen["url"]
    await c.aclose()


async def test_compliance_events_omits_none_filters():
    def handler(req):
        # no filters supplied -> empty query string
        assert req.url.query in (b"", "")
        return httpx.Response(200, json={"total": 0, "items": []})

    c = _client(handler)
    r = await c.compliance_events()
    assert r.ok
    await c.aclose()


async def test_compliance_evaluate_posts_body():
    seen = {}

    def handler(req):
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.read().decode()
        return httpx.Response(200, json={"created": 1, "updated": 0})

    c = _client(handler)
    r = await c.compliance_evaluate(7, "2026-05-01T00:00:00", "2026-06-01T00:00:00")
    assert r.ok
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/compliance/evaluate"
    assert '"permit_id"' in seen["body"]
    assert '"start"' in seen["body"]
    assert '"end"' in seen["body"]
    await c.aclose()
