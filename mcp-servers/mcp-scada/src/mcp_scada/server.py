import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

SCADA_API_URL = os.environ.get("SCADA_API_URL", "http://localhost:8001")
SCADA_TOKEN = os.environ.get("SCADA_TOKEN", "")

server = Server("ekont-scada")


async def _api(path: str, params: dict[str, Any] | None = None) -> Any:
    headers = {"Authorization": f"Bearer {SCADA_TOKEN}"} if SCADA_TOKEN else {}
    async with httpx.AsyncClient(base_url=SCADA_API_URL, headers=headers) as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()


async def _api_post(path: str, body: dict[str, Any]) -> Any:
    headers = {"Authorization": f"Bearer {SCADA_TOKEN}"} if SCADA_TOKEN else {}
    async with httpx.AsyncClient(base_url=SCADA_API_URL, headers=headers) as c:
        r = await c.post(path, json=body)
        r.raise_for_status()
        return r.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_current_values",
            description="Get the latest reading for all active tags or a specific subset. Returns tag name, value, unit, timestamp, and quality.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tag names to filter by (e.g. ['PT-101', 'FT-201']). Returns all active tags if empty.",
                    }
                },
            },
        ),
        Tool(
            name="query_trend",
            description="Fetch historical trend data for one or more tags over a time range with optional aggregation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tag names to query",
                    },
                    "start": {
                        "type": "string",
                        "description": "ISO 8601 start time (e.g. 2026-06-16T00:00:00Z)",
                    },
                    "end": {
                        "type": "string",
                        "description": "ISO 8601 end time (e.g. 2026-06-17T00:00:00Z)",
                    },
                    "bucket": {
                        "type": "string",
                        "description": "Aggregation bucket (e.g. 1h, 1d, 15min)",
                        "default": "raw",
                    },
                },
                "required": ["tags", "start", "end"],
            },
        ),
        Tool(
            name="generate_report",
            description="Generate a data report. Returns a download URL for the resulting file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tag names to include",
                    },
                    "start": {"type": "string", "description": "ISO 8601 start"},
                    "end": {"type": "string", "description": "ISO 8601 end"},
                    "format": {
                        "type": "string",
                        "enum": ["excel", "pdf", "json", "csv"],
                        "default": "excel",
                    },
                    "aggregation": {
                        "type": "string",
                        "enum": ["raw", "hourly", "daily", "monthly"],
                        "default": "raw",
                    },
                },
                "required": ["tags", "start", "end"],
            },
        ),
        Tool(
            name="list_tags",
            description="List all configured tags with metadata: name, unit, device, PLC, active status, deadband settings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Optional search term to filter tags by name",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "Only return active tags",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="list_plcs",
            description="List all configured PLCs with connection status, IP, rack, and slot.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="run_sql_query",
            description="Run a read-only SQL query on the time-series database. Only SELECT, WITH, and EXPLAIN statements are allowed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query (SELECT / WITH / EXPLAIN only)",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="detect_anomalies",
            description="Run anomaly detection on a tag's recent data. Returns timestamps and values that deviate significantly from the norm using z-score analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag_name": {
                        "type": "string",
                        "description": "Tag name to analyze",
                    },
                    "window": {
                        "type": "string",
                        "description": "Lookback window (e.g. 7d, 24h)",
                        "default": "7d",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Z-score threshold (default 3.0)",
                        "default": 3.0,
                    },
                },
                "required": ["tag_name"],
            },
        ),
        Tool(
            name="predict_trend",
            description="Forecast future values for a tag using linear regression on recent history.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag_name": {
                        "type": "string",
                        "description": "Tag name to forecast",
                    },
                    "horizon": {
                        "type": "string",
                        "description": "Forecast horizon (e.g. 24h, 7d)",
                        "default": "24h",
                    },
                },
                "required": ["tag_name"],
            },
        ),
        Tool(
            name="get_system_health",
            description="Get overall system health including PLC connection status, tag counts, and database size.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="resolve_tag",
            description="Search for tags by partial name match (fuzzy). Useful when an agent needs to find the exact tag name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Partial tag name or description to search for",
                    }
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[TextContent | ImageContent | EmbeddedResource]:
    if name == "query_current_values":
        tag_names = arguments.get("tag_names", [])
        params = {"tag_names": ",".join(tag_names)} if tag_names else {}
        data = await _api("/api/dashboard/current-values", params)
        return [TextContent(type="text", text=str(data))]

    if name == "query_trend":
        tags = arguments["tags"]
        start = arguments["start"]
        end = arguments["end"]
        bucket = arguments.get("bucket", "raw")
        params = {
            "tags": ",".join(tags),
            "start": start,
            "end": end,
            "bucket": bucket,
        }
        data = await _api("/api/dashboard/trend", params)
        return [TextContent(type="text", text=str(data))]

    if name == "generate_report":
        body = {
            "tags": arguments["tags"],
            "start": arguments["start"],
            "end": arguments["end"],
            "format": arguments.get("format", "excel"),
            "aggregation": arguments.get("aggregation", "raw"),
        }
        data = await _api_post("/api/ai/reports/generate", body)
        return [TextContent(type="text", text=str(data))]

    if name == "list_tags":
        params = {}
        if "search" in arguments:
            params["search"] = arguments["search"]
        if "active_only" in arguments:
            params["active_only"] = "true" if arguments["active_only"] else "false"
        data = await _api("/api/tags/", params)
        return [TextContent(type="text", text=str(data))]

    if name == "list_plcs":
        data = await _api("/api/plc/")
        return [TextContent(type="text", text=str(data))]

    if name == "run_sql_query":
        body = {"query": arguments["query"]}
        data = await _api_post("/api/query/", body)
        return [TextContent(type="text", text=str(data))]

    if name == "detect_anomalies":
        body = {
            "tag_name": arguments["tag_name"],
            "window": arguments.get("window", "7d"),
            "threshold": arguments.get("threshold", 3.0),
        }
        data = await _api_post("/api/ai/anomalies", body)
        return [TextContent(type="text", text=str(data))]

    if name == "predict_trend":
        body = {
            "tag_name": arguments["tag_name"],
            "horizon": arguments.get("horizon", "24h"),
        }
        data = await _api_post("/api/ai/predict", body)
        return [TextContent(type="text", text=str(data))]

    if name == "get_system_health":
        health = await _api("/health")
        plc_data = await _api("/api/plc/")
        tag_data = await _api("/api/tags/", {"active_only": "true"})
        result = {
            "health": health,
            "plc_count": len(plc_data) if isinstance(plc_data, list) else 0,
            "active_tags": len(tag_data) if isinstance(tag_data, list) else 0,
        }
        return [TextContent(type="text", text=str(result))]

    if name == "resolve_tag":
        query = arguments["query"]
        data = await _api("/api/tags/", {"search": query})
        return [TextContent(type="text", text=str(data))]

    raise ValueError(f"Unknown tool: {name}")


@server.list_prompts()
async def list_prompts():
    return []


@server.list_resources()
async def list_resources():
    return []
