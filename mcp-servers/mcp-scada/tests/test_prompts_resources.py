import json

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
    assert "scada://agent/contract" in uris
    assert "scada://agent/capabilities" in uris
    assert "scada://agent/bootstrap" in uris
    assert "scada://health" in uris


@pytest.mark.asyncio
async def test_agent_contract_resources_return_json_envelopes():
    contract = json.loads(await srv.agent_contract_resource())
    capabilities = json.loads(await srv.agent_capabilities_resource())

    assert contract["ok"] is True
    assert contract["data"]["project"] == "ekont-smart-report"
    assert "scada://agent/capabilities" in contract["data"]["mcp"]["resources"]

    assert capabilities["ok"] is True
    assert capabilities["data"]["counts"]["total"] == len(
        capabilities["data"]["capabilities"]
    )
    assert any(
        cap["name"] == "list_tags" and cap["surfaces"]["mcp_tool"]
        for cap in capabilities["data"]["capabilities"]
    )
