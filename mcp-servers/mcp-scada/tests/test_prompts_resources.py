import pytest
from mcp_scada import server as srv


@pytest.mark.asyncio
async def test_prompts_registered():
    prompts = await srv.mcp.list_prompts()
    names = {p.name for p in prompts}
    assert {
        "analyze_tag",
        "daily_report",
        "system_health_check",
        "agent_session_triage",
    } <= names


@pytest.mark.asyncio
async def test_resources_registered():
    resources = await srv.mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "scada://tags" in uris
    assert "scada://schema" in uris
    assert "scada://plcs" in uris
