from __future__ import annotations

from typing import Any

from .catalog import CAPABILITIES

BASE_RESOURCE_URIS: tuple[str, ...] = ("scada://tags", "scada://plcs", "scada://schema")
AGENT_RESOURCE_URIS: tuple[str, ...] = (
    "scada://agent/contract",
    "scada://agent/capabilities",
    "scada://agent/bootstrap",
    "scada://health",
)
TIER_ORDER: tuple[str, ...] = ("read", "write", "destructive")


def _tier_counts(capabilities: list[dict[str, Any]]) -> dict[str, int]:
    counts = {tier: 0 for tier in TIER_ORDER}
    for cap in capabilities:
        counts[cap["tier"]] = counts.get(cap["tier"], 0) + 1
    return counts


def build_agent_capabilities(mcp_allowed_tiers: set[str] | None = None) -> dict[str, Any]:
    allowed = mcp_allowed_tiers or {"read"}
    capabilities = [
        {
            "name": cap.name,
            "description": cap.description,
            "tier": cap.tier,
            "input_schema": cap.input_schema,
            "surfaces": {
                "mcp_tool": cap.tier in allowed,
                "core_catalog": True,
            },
        }
        for cap in CAPABILITIES
    ]
    by_tier = _tier_counts(capabilities)
    return {
        "schema_version": "1.0",
        "capabilities": capabilities,
        "counts": {
            "total": len(capabilities),
            "by_tier": by_tier,
            "mcp_enabled": sum(1 for cap in capabilities if cap["surfaces"]["mcp_tool"]),
        },
    }


def build_agent_contract(
    api_url: str = "http://localhost:8001",
    mcp_allowed_tiers: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "ekont-smart-report",
        "api_url": api_url,
        "defaults": {
            "json_output_flag": "--json-output",
            "api_env": "SCADA_API_URL",
            "token_env": "SCADA_TOKEN",
        },
        "cli": {
            "binary": "scada",
            "recommended_start": [
                "scada agent bootstrap --json-output",
                "scada doctor --json-output",
                "scada agent capabilities --json-output",
            ],
            "stable_agent_commands": [
                "scada agent bootstrap --json-output",
                "scada agent capabilities --json-output",
                "scada agent contract --json-output",
                "scada doctor --json-output",
            ],
        },
        "mcp": {
            "server": "scada",
            "resources": [*BASE_RESOURCE_URIS, *AGENT_RESOURCE_URIS],
            "tools_source": "scada_core.catalog",
            "enabled_tiers": sorted(mcp_allowed_tiers or {"read"}),
            "write_env_flags": {
                "write": "SCADA_MCP_ALLOW_WRITES=1",
                "destructive": "SCADA_MCP_ALLOW_DESTRUCTIVE=1",
            },
        },
        "safety": {
            "read_tier_default": True,
            "writes_require_env": True,
            "destructive_requires_write_and_destructive_env": True,
        },
    }


def build_agent_bootstrap(
    *,
    api_url: str,
    token_present: bool,
    token_source: str,
    health: Any,
    ready: Any,
    system: Any,
    mcp_allowed_tiers: set[str] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if not token_present:
        issues.append(
            {
                "kind": "auth",
                "severity": "warning",
                "message": "No SCADA token is available; write commands and user context are limited.",
            }
        )
    if isinstance(health, dict) and health.get("error"):
        issues.append(
            {
                "kind": "health",
                "severity": "error",
                "message": health.get("detail", "API health check failed"),
            }
        )
    if isinstance(ready, dict) and ready.get("status") != "ready":
        issues.append(
            {
                "kind": "ready",
                "severity": "error",
                "message": "Readiness checks are not complete.",
            }
        )
    if isinstance(system, dict) and system.get("error"):
        issues.append(
            {
                "kind": "system",
                "severity": "warning",
                "message": system.get("detail", "System health check failed"),
            }
        )

    status = "ok"
    if any(issue["severity"] == "error" for issue in issues):
        status = "error"
    elif issues:
        status = "warning"

    next_commands = [
        "scada doctor --json-output",
        "scada agent capabilities --json-output",
        "scada dashboard overview --json-output",
    ]
    if not token_present:
        next_commands.insert(0, "scada auth login admin")

    return {
        "schema_version": "1.0",
        "status": status,
        "api_url": api_url,
        "token": {"present": token_present, "source": token_source},
        "health": health,
        "ready": ready,
        "system": system,
        "issues": issues,
        "next_commands": next_commands,
        "contract": build_agent_contract(api_url, mcp_allowed_tiers),
        "capabilities": build_agent_capabilities(mcp_allowed_tiers),
    }
