from scada_core.agent_contract import (
    AGENT_RESOURCE_URIS,
    build_agent_bootstrap,
    build_agent_capabilities,
    build_agent_contract,
)


def test_agent_capabilities_describe_catalog_and_mcp_enabled_state():
    data = build_agent_capabilities(mcp_allowed_tiers={"read"})

    assert data["schema_version"] == "1.0"
    assert data["counts"]["total"] == len(data["capabilities"])
    assert data["counts"]["by_tier"]["read"] > 0
    assert data["counts"]["mcp_enabled"] == data["counts"]["by_tier"]["read"]

    by_name = {cap["name"]: cap for cap in data["capabilities"]}
    assert by_name["list_tags"]["tier"] == "read"
    assert by_name["list_tags"]["surfaces"]["mcp_tool"] is True
    assert by_name["delete_tag"]["tier"] == "destructive"
    assert by_name["delete_tag"]["surfaces"]["mcp_tool"] is False


def test_agent_contract_lists_stable_cli_and_mcp_entrypoints():
    data = build_agent_contract(api_url="http://api", mcp_allowed_tiers={"read"})

    assert data["schema_version"] == "1.0"
    assert data["project"] == "ekont-smart-report"
    assert data["api_url"] == "http://api"
    assert "scada agent bootstrap --json-output" in data["cli"]["recommended_start"]
    assert set(AGENT_RESOURCE_URIS) <= set(data["mcp"]["resources"])
    assert data["mcp"]["write_env_flags"] == {
        "write": "SCADA_MCP_ALLOW_WRITES=1",
        "destructive": "SCADA_MCP_ALLOW_DESTRUCTIVE=1",
    }


def test_agent_bootstrap_combines_status_and_next_steps():
    data = build_agent_bootstrap(
        api_url="http://api",
        token_present=False,
        token_source="missing",
        health={"status": "ok"},
        ready={"status": "ready"},
        system={"tag_count": 3, "plc_count": 1},
        mcp_allowed_tiers={"read"},
    )

    assert data["status"] == "warning"
    assert data["token"] == {"present": False, "source": "missing"}
    assert data["health"]["status"] == "ok"
    assert data["ready"]["status"] == "ready"
    assert data["system"]["tag_count"] == 3
    assert data["issues"][0]["kind"] == "auth"
    assert data["next_commands"][0] == "scada auth login admin"
