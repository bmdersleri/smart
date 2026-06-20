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
async def test_default_is_read_only(monkeypatch):
    srv = _reload_server(monkeypatch)
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" not in names
    assert "delete_tag" not in names
    assert "list_tags" in names  # read tools still present


@pytest.mark.asyncio
async def test_writes_flag_enables_write_not_destructive(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" in names  # write
    assert "template_create" in names  # write
    assert "delete_tag" not in names  # destructive still gated
    assert "user_delete" not in names


@pytest.mark.asyncio
async def test_destructive_requires_both_flags(monkeypatch):
    srv = _reload_server(monkeypatch, writes="1", destructive="1")
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "delete_tag" in names
    assert "user_delete" in names


@pytest.mark.asyncio
async def test_destructive_alone_does_nothing(monkeypatch):
    srv = _reload_server(monkeypatch, destructive="1")  # writes not set
    names = {t.name for t in await srv.mcp.list_tools()}
    assert "watchlist_add" not in names
    assert "delete_tag" not in names


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    import importlib
    import mcp_scada.server as srv

    monkeypatch.delenv("SCADA_MCP_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("SCADA_MCP_ALLOW_DESTRUCTIVE", raising=False)
    importlib.reload(srv)
