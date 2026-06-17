import os

import asyncpg
from mcp.server import Server
from mcp.types import Tool, TextContent

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter",
)

server = Server("ekont-scada-db")


def _parse_dsn(dsn: str) -> dict:
    raw = dsn.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
    user_pass, rest = raw.split("@", 1)
    user, pw = user_pass.split(":", 1)
    host_port, database = rest.split("/", 1)
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")
    return {
        "user": user,
        "password": pw,
        "host": host,
        "port": int(port),
        "database": database.split("?")[0],
    }


async def _query(sql: str) -> list[dict]:
    dsn = _parse_dsn(DATABASE_URL)
    conn = await asyncpg.connect(**dsn)
    try:
        rows = await conn.fetch(sql)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_tables",
            description="List all tables and views in the database with schema name and row count estimate.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="describe_table",
            description="Get column names, data types, nullable status, and default values for a table.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Table name (e.g. tags, tag_readings, users)",
                    },
                    "schema": {
                        "type": "string",
                        "description": "Schema name (default: public)",
                        "default": "public",
                    },
                },
                "required": ["table_name"],
            },
        ),
        Tool(
            name="get_tag_schema",
            description="Get the full tags catalog schema including column names, types, and constraints.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_hypertables",
            description="List TimescaleDB hypertables and their chunk sizes.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="run_schema_query",
            description="Run a read-only information_schema query to explore the database structure.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query against information_schema or pg_catalog",
                    }
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_tables":
        rows = await _query(
            "SELECT table_schema, table_name, "
            "pg_size_pretty(pg_total_relation_size(quote_ident(table_schema)||'.'||quote_ident(table_name))) AS size "
            "FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )
        return [TextContent(type="text", text=str(rows))]

    if name == "describe_table":
        table = arguments["table_name"]
        schema = arguments.get("schema", "public")
        rows = await _query(
            f"SELECT column_name, data_type, is_nullable, column_default, "
            f"character_maximum_length "
            f"FROM information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
            f"ORDER BY ordinal_position"
        )
        return [TextContent(type="text", text=str(rows))]

    if name == "get_tag_schema":
        rows = await _query(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'tags' "
            "ORDER BY ordinal_position"
        )
        return [TextContent(type="text", text=str(rows))]

    if name == "list_hypertables":
        rows = await _query(
            "SELECT hypertable_name, num_chunks, "
            "pg_size_pretty(hypertable_size(quote_ident(hypertable_schema)||'.'||quote_ident(hypertable_name))) AS total_size "
            "FROM timescaledb_information.hypertables "
            "ORDER BY hypertable_name"
        )
        return [TextContent(type="text", text=str(rows))]

    if name == "run_schema_query":
        query = arguments["query"].lower()
        allowed = ("information_schema", "pg_catalog", "timescaledb_information")
        if not any(a in query for a in allowed):
            return [
                TextContent(
                    type="text",
                    text="Error: only information_schema, pg_catalog, or timescaledb_information queries allowed",
                )
            ]
        rows = await _query(arguments["query"])
        return [TextContent(type="text", text=str(rows))]

    raise ValueError(f"Unknown tool: {name}")


@server.list_prompts()
async def list_prompts():
    return []


@server.list_resources()
async def list_resources():
    return []
