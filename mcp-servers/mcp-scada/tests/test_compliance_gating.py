import importlib

import pytest


def _reload_server(monkeypatch, writes=None, destructive=None):
    if writes is None:
        monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    else:
        monkeypatch.setenv("SCADA_MCP_ALLOW_WRITES", writes)
    if destructive is None:
        monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    else:
        monkeypatch.setenv("SCADA_MCP_ALLOW_DESTRUCTIVE", destructive)
    import mcp_scada.server as srv

    return importlib.reload(srv)


@pytest.mark.asyncio
async def test_compliance_reads_registered_by_default(monkeypatch):
    srv = _reload_server(monkeypatch)
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "compliance_overview" in names
    assert "compliance_list_events" in names
    assert "compliance_evaluate" not in names  # write-gated


@pytest.mark.asyncio
async def test_compliance_evaluate_requires_writes_flag(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "compliance_evaluate" in names
    assert "compliance_overview" in names
    assert "compliance_list_events" in names


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    import importlib

    import mcp_scada.server as srv

    monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    importlib.reload(srv)
