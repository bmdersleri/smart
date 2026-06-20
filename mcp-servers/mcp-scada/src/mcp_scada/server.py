from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from scada_core.catalog import CAPABILITIES, CATALOG
from scada_core.client import AsyncScadaClient
from scada_core.formatting import to_json

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
    finally:
        await client.aclose()
    return to_json(result)


def _make_tool(cap_name: str):
    async def _tool(arguments: dict | None = None) -> str:
        return await call_capability(cap_name, arguments or {})

    _tool.__name__ = cap_name
    return _tool


def _register() -> None:
    for cap in CAPABILITIES:
        mcp.add_tool(
            _make_tool(cap.name),
            name=cap.name,
            description=cap.description,
        )


_register()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
