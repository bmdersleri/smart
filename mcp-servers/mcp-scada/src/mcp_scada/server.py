from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import Prompt

from scada_core.catalog import CATALOG
from scada_core.client import AsyncScadaClient
from scada_core.envelope import fail
from scada_core.formatting import to_json
from scada_core.prompts import PROMPTS

SCADA_API_URL = os.environ.get("SCADA_API_URL", "http://localhost:8001")
SCADA_TOKEN = os.environ.get("SCADA_TOKEN", "") or None

mcp = FastMCP("ekont-scada")


def _make_client() -> AsyncScadaClient:
    return AsyncScadaClient(base_url=SCADA_API_URL, token=SCADA_TOKEN)


async def call_capability(name: str, args: dict) -> str:
    cap = CATALOG[name]
    client = _make_client()
    try:
        result = await cap.handler(client, args)
    except Exception as exc:
        result = fail("error", str(exc))
    finally:
        await client.aclose()
    return to_json(result)


# ---------------------------------------------------------------------------
# Typed per-capability tool functions
# FastMCP derives the input JSON schema from each function's signature,
# which restores typed parameters for MCP clients.
# ---------------------------------------------------------------------------


async def query_current_values(tag_names: list[str] | None = None) -> str:
    return await call_capability("query_current_values", {"tag_names": tag_names})


async def query_trend(tags: list[str], start: str, end: str) -> str:
    return await call_capability(
        "query_trend", {"tags": tags, "start": start, "end": end}
    )


async def generate_report(
    tags: list[str],
    start: str,
    end: str,
    format: str = "excel",
    aggregation: str = "raw",
) -> str:
    return await call_capability(
        "generate_report",
        {
            "tags": tags,
            "start": start,
            "end": end,
            "format": format,
            "aggregation": aggregation,
        },
    )


async def list_tags() -> str:
    return await call_capability("list_tags", {})


async def list_plcs() -> str:
    return await call_capability("list_plcs", {})


async def run_sql_query(query: str) -> str:
    return await call_capability("run_sql_query", {"query": query})


async def detect_anomalies(
    tag_name: str, window: str = "7d", threshold: float = 3.0
) -> str:
    return await call_capability(
        "detect_anomalies",
        {"tag_name": tag_name, "window": window, "threshold": threshold},
    )


async def predict_trend(tag_name: str, horizon: str = "24h") -> str:
    return await call_capability(
        "predict_trend", {"tag_name": tag_name, "horizon": horizon}
    )


async def get_system_health() -> str:
    return await call_capability("get_system_health", {})


async def resolve_tag(query: str) -> str:
    return await call_capability("resolve_tag", {"query": query})


# Register each tool with its capability name and description from the catalog.
_TOOL_REGISTRY = [
    (query_current_values, "query_current_values"),
    (query_trend, "query_trend"),
    (generate_report, "generate_report"),
    (list_tags, "list_tags"),
    (list_plcs, "list_plcs"),
    (run_sql_query, "run_sql_query"),
    (detect_anomalies, "detect_anomalies"),
    (predict_trend, "predict_trend"),
    (get_system_health, "get_system_health"),
    (resolve_tag, "resolve_tag"),
]

for _fn, _cap_name in _TOOL_REGISTRY:
    mcp.add_tool(_fn, name=_cap_name, description=CATALOG[_cap_name].description)


def _register_prompts() -> None:
    """Register workflow prompt templates from scada_core.prompts."""
    for pname, template in PROMPTS.items():

        def make_handler(t: str):
            def handler(**kwargs: str) -> str:
                return t.format_map(kwargs)

            return handler

        prompt = Prompt.from_function(make_handler(template), name=pname)
        mcp.add_prompt(prompt)


def _register_resources() -> None:
    """Register read-only SCADA data resources."""

    @mcp.resource("scada://tags")
    async def _tags() -> str:
        client = _make_client()
        try:
            return to_json(await client.list_tags())
        finally:
            await client.aclose()

    @mcp.resource("scada://plcs")
    async def _plcs() -> str:
        client = _make_client()
        try:
            return to_json(await client.list_plcs())
        finally:
            await client.aclose()

    @mcp.resource("scada://schema")
    async def _schema() -> str:
        client = _make_client()
        try:
            return to_json(await client.explore_schema())
        finally:
            await client.aclose()


_register_prompts()
_register_resources()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
