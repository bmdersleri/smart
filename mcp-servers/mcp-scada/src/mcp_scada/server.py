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


# ---------------------------------------------------------------------------
# Write / destructive tool functions
# ---------------------------------------------------------------------------


def _allowed_tiers() -> set[str]:
    tiers = {"read"}
    if os.environ.get("SCADA_MCP_ALLOW_WRITES") == "1":
        tiers.add("write")
        if os.environ.get("SCADA_MCP_ALLOW_DESTRUCTIVE") == "1":
            tiers.add("destructive")
    return tiers


async def update_tag(
    tag_id: int,
    unit: str | None = None,
    device: str | None = None,
    channel: str | None = None,
    description: str | None = None,
    min_alarm: float | None = None,
    max_alarm: float | None = None,
) -> str:
    return await call_capability(
        "update_tag",
        {
            "tag_id": tag_id,
            "unit": unit,
            "device": device,
            "channel": channel,
            "description": description,
            "min_alarm": min_alarm,
            "max_alarm": max_alarm,
        },
    )


async def delete_tag(tag_id: int) -> str:
    return await call_capability("delete_tag", {"tag_id": tag_id})


async def watchlist_add(tag_id: int) -> str:
    return await call_capability("watchlist_add", {"tag_id": tag_id})


async def watchlist_remove(tag_id: int) -> str:
    return await call_capability("watchlist_remove", {"tag_id": tag_id})


async def annotation_add(ts: str, text: str, tag_id: int | None = None) -> str:
    return await call_capability(
        "annotation_add", {"ts": ts, "text": text, "tag_id": tag_id}
    )


async def annotation_delete(annotation_id: int) -> str:
    return await call_capability("annotation_delete", {"annotation_id": annotation_id})


async def template_create(payload: dict) -> str:
    return await call_capability("template_create", {"payload": payload})


async def template_update(template_id: int, payload: dict) -> str:
    return await call_capability(
        "template_update", {"template_id": template_id, "payload": payload}
    )


async def template_run(
    template_id: int, start: str | None = None, end: str | None = None
) -> str:
    return await call_capability(
        "template_run", {"template_id": template_id, "start": start, "end": end}
    )


async def template_delete(template_id: int) -> str:
    return await call_capability("template_delete", {"template_id": template_id})


async def scheduled_create(payload: dict) -> str:
    return await call_capability("scheduled_create", {"payload": payload})


async def scheduled_update(scheduled_id: int, payload: dict) -> str:
    return await call_capability(
        "scheduled_update", {"scheduled_id": scheduled_id, "payload": payload}
    )


async def scheduled_toggle(scheduled_id: int) -> str:
    return await call_capability("scheduled_toggle", {"scheduled_id": scheduled_id})


async def scheduled_delete(scheduled_id: int) -> str:
    return await call_capability("scheduled_delete", {"scheduled_id": scheduled_id})


async def archive_delete(archive_id: int) -> str:
    return await call_capability("archive_delete", {"archive_id": archive_id})


async def group_create(
    name: str, parent_id: int | None = None, sort_order: int = 0
) -> str:
    return await call_capability(
        "group_create", {"name": name, "parent_id": parent_id, "sort_order": sort_order}
    )


async def group_update(
    group_id: int,
    name: str | None = None,
    parent_id: int | None = None,
    sort_order: int | None = None,
) -> str:
    return await call_capability(
        "group_update",
        {
            "group_id": group_id,
            "name": name,
            "parent_id": parent_id,
            "sort_order": sort_order,
        },
    )


async def group_assign(group_id: int, tag_ids: list[int]) -> str:
    return await call_capability(
        "group_assign", {"group_id": group_id, "tag_ids": tag_ids}
    )


async def group_unassign(tag_ids: list[int]) -> str:
    return await call_capability("group_unassign", {"tag_ids": tag_ids})


async def group_delete(group_id: int) -> str:
    return await call_capability("group_delete", {"group_id": group_id})


async def plc_create(name: str, ip: str = "", rack: int = 0, slot: int = 1) -> str:
    return await call_capability(
        "plc_create", {"name": name, "ip": ip, "rack": rack, "slot": slot}
    )


async def plc_update(name: str, ip: str, rack: int = 0, slot: int = 1) -> str:
    return await call_capability(
        "plc_update", {"name": name, "ip": ip, "rack": rack, "slot": slot}
    )


async def plc_delete(name: str) -> str:
    return await call_capability("plc_delete", {"name": name})


async def user_create(
    username: str,
    email: str,
    password: str,
    full_name: str = "",
    role: str = "operator",
) -> str:
    return await call_capability(
        "user_create",
        {
            "username": username,
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
        },
    )


async def user_update(
    user_id: int,
    email: str | None = None,
    full_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> str:
    return await call_capability(
        "user_update",
        {
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
        },
    )


async def user_set_password(user_id: int, password: str) -> str:
    return await call_capability(
        "user_set_password", {"user_id": user_id, "password": password}
    )


async def user_delete(user_id: int) -> str:
    return await call_capability("user_delete", {"user_id": user_id})


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
    (update_tag, "update_tag"),
    (delete_tag, "delete_tag"),
    (watchlist_add, "watchlist_add"),
    (watchlist_remove, "watchlist_remove"),
    (annotation_add, "annotation_add"),
    (annotation_delete, "annotation_delete"),
    (template_create, "template_create"),
    (template_update, "template_update"),
    (template_run, "template_run"),
    (template_delete, "template_delete"),
    (scheduled_create, "scheduled_create"),
    (scheduled_update, "scheduled_update"),
    (scheduled_toggle, "scheduled_toggle"),
    (scheduled_delete, "scheduled_delete"),
    (archive_delete, "archive_delete"),
    (group_create, "group_create"),
    (group_update, "group_update"),
    (group_assign, "group_assign"),
    (group_unassign, "group_unassign"),
    (group_delete, "group_delete"),
    (plc_create, "plc_create"),
    (plc_update, "plc_update"),
    (plc_delete, "plc_delete"),
    (user_create, "user_create"),
    (user_update, "user_update"),
    (user_set_password, "user_set_password"),
    (user_delete, "user_delete"),
]


def _register() -> None:
    allowed = _allowed_tiers()
    for fn, cap_name in _TOOL_REGISTRY:
        if CATALOG[cap_name].tier in allowed:
            mcp.add_tool(fn, name=cap_name, description=CATALOG[cap_name].description)


_register()


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
