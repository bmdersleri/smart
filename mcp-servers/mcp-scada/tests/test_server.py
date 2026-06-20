import httpx
import pytest
from mcp_scada import server as srv
from scada_core.catalog import CATALOG


@pytest.mark.asyncio
async def test_all_catalog_tools_registered():
    tools = await srv.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(CATALOG)


@pytest.mark.asyncio
async def test_call_tool_returns_json_text(monkeypatch):
    def handler(req):
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    monkeypatch.setattr(
        srv,
        "_make_client",
        lambda: __import__(
            "scada_core.client", fromlist=["AsyncScadaClient"]
        ).AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler)),
    )
    result = await srv.call_capability("list_tags", {})
    assert '"PT-101"' in result  # JSON, repr değil
    assert "isError" not in result


@pytest.mark.asyncio
async def test_call_tool_error_is_marked(monkeypatch):
    def handler(req):
        return httpx.Response(500, json={"detail": "boom"})

    monkeypatch.setattr(
        srv,
        "_make_client",
        lambda: __import__(
            "scada_core.client", fromlist=["AsyncScadaClient"]
        ).AsyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler)),
    )
    result = await srv.call_capability("list_plcs", {})
    assert '"ok": false' in result.lower()


@pytest.mark.asyncio
async def test_tools_expose_typed_parameter_schemas():
    tools = await srv.mcp.list_tools()
    by = {t.name: t for t in tools}
    # detect_anomalies must advertise its real params, not an opaque dict
    props = by["detect_anomalies"].inputSchema["properties"]
    assert "tag_name" in props
    assert "window" in props and "threshold" in props
    # query_trend requires tags/start/end
    qt = by["query_trend"].inputSchema
    assert "tags" in qt["properties"] and "start" in qt["properties"]
    assert set(qt.get("required", [])) >= {"tags", "start", "end"}
