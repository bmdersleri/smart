from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/query", tags=["query"])

SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
EXPLAIN_RE = re.compile(r"^\s*EXPLAIN\b", re.IGNORECASE)
WITH_RE = re.compile(r"^\s*WITH\b", re.IGNORECASE)


class QueryRequest(BaseModel):
    sql: str
    params: dict | None = None
    limit: int = 5000


def _has_multiple_statements(sql: str) -> bool:
    """Conservative single-statement guard.

    A final trailing semicolon is accepted for convenience; any earlier
    semicolon outside strings/comments is rejected.
    """
    statement_ended = False
    quote: str | None = None
    dollar_quote: str | None = None
    line_comment = False
    block_comment = False
    i = 0

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if line_comment:
            if ch in "\r\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue

        if dollar_quote:
            if sql.startswith(dollar_quote, i):
                i += len(dollar_quote)
                dollar_quote = None
                continue
            i += 1
            continue

        if quote:
            if ch == quote:
                if nxt == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if ch == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if match:
                dollar_quote = match.group(0)
                i += len(dollar_quote)
                continue
        if ch == ";":
            statement_ended = True
            i += 1
            continue
        if statement_ended and not ch.isspace():
            return True
        i += 1

    return False


def _result_metadata(*, returned_row_count: int, fetched_row_count: int, limit: int) -> dict:
    truncated = fetched_row_count > limit
    return {
        "row_count": returned_row_count,
        "returned_row_count": returned_row_count,
        "minimum_row_count": fetched_row_count if truncated else returned_row_count,
        "row_count_is_exact": not truncated,
        "truncated": truncated,
    }


def _effective_limit(requested: int) -> int:
    if requested <= 0:
        raise HTTPException(status_code=400, detail="limit pozitif olmalıdır")
    return min(requested, settings.QUERY_MAX_ROWS)


async def _apply_statement_timeout(db: AsyncSession) -> None:
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "postgresql" and settings.QUERY_STATEMENT_TIMEOUT_MS > 0:
        timeout_ms = max(0, int(settings.QUERY_STATEMENT_TIMEOUT_MS))
        await db.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))


@router.post("/run")
async def run_query(
    req: QueryRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    """Read-only SQL sorgusu calistir. Sadece SELECT/WITH/EXPLAIN."

    Agent'larin veriyi kendi sorgulariyla kesfetmesi icin.
    """
    stripped = req.sql.strip()
    if len(stripped) > settings.QUERY_MAX_SQL_CHARS:
        raise HTTPException(status_code=400, detail="SQL sorgusu çok uzun")
    if _has_multiple_statements(stripped):
        raise HTTPException(status_code=400, detail="Tek sorguya izin verilir")
    if not (SELECT_RE.match(stripped) or WITH_RE.match(stripped) or EXPLAIN_RE.match(stripped)):
        raise HTTPException(
            status_code=400, detail="Sadece SELECT/WITH/EXPLAIN sorgularina izin verilir"
        )

    for kw in (
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "CALL",
        "MERGE",
    ):
        if re.search(rf"\b{kw}\b", stripped, re.IGNORECASE):
            raise HTTPException(status_code=400, detail=f"Yasak: {kw} sorgularina izin verilmez")

    limit = _effective_limit(req.limit)
    try:
        await _apply_statement_timeout(db)
        result = await db.execute(text(stripped), req.params or {})
        rows = result.fetchmany(limit + 1)
        visible_rows = rows[:limit]
        if stripped.upper().startswith("EXPLAIN"):
            return {
                "query": req.sql,
                "columns": list(visible_rows[0]._fields) if visible_rows else [],
                "rows": [dict(r._mapping) for r in visible_rows],
                **_result_metadata(
                    returned_row_count=len(visible_rows),
                    fetched_row_count=len(rows),
                    limit=limit,
                ),
            }

        columns = list(visible_rows[0]._fields) if visible_rows else []
        data = [dict(r._mapping) for r in visible_rows]

        return {
            "query": req.sql,
            "columns": columns,
            "rows": data,
            **_result_metadata(
                returned_row_count=len(data),
                fetched_row_count=len(rows),
                limit=limit,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sorgu hatasi: {e}") from e
