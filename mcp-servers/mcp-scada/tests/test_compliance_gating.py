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


_COMPLIANCE_WRITES = (
    "compliance_evaluate",
    "compliance_add_note",
    "compliance_set_status",
    "compliance_create_report_pack",
    "compliance_approve_report_pack",
)


@pytest.mark.asyncio
async def test_compliance_reads_registered_by_default(monkeypatch):
    srv = _reload_server(monkeypatch)
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "compliance_overview" in names
    assert "compliance_list_events" in names
    assert "compliance_ask" in names  # assistant is read, default-on
    for write_tool in _COMPLIANCE_WRITES:
        assert write_tool not in names  # write-gated


@pytest.mark.asyncio
async def test_compliance_evaluate_requires_writes_flag(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "compliance_evaluate" in names
    assert "compliance_overview" in names
    assert "compliance_list_events" in names


@pytest.mark.asyncio
async def test_compliance_writes_require_writes_flag(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "compliance_ask" in names  # read stays available
    for write_tool in _COMPLIANCE_WRITES:
        assert write_tool in names


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    import importlib

    import mcp_scada.server as srv

    monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    importlib.reload(srv)
