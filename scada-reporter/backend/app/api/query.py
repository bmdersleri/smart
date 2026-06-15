from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.core.database import get_db

router = APIRouter(prefix="/query", tags=["query"])

SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
EXPLAIN_RE = re.compile(r"^\s*EXPLAIN\b", re.IGNORECASE)
WITH_RE = re.compile(r"^\s*WITH\b", re.IGNORECASE)


class QueryRequest(BaseModel):
    sql: str
    params: dict | None = None
    limit: int = 5000


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

    try:
        result = await db.execute(text(stripped), req.params or {})
        if stripped.upper().startswith("EXPLAIN"):
            rows = result.all()
            return {
                "query": req.sql,
                "columns": list(rows[0]._fields) if rows else [],
                "rows": [dict(r._mapping) for r in rows[: req.limit]],
                "row_count": len(rows),
            }

        rows = result.all()
        columns = list(rows[0]._fields) if rows else []
        data = [dict(r._mapping) for r in rows[: req.limit]]

        return {
            "query": req.sql,
            "columns": columns,
            "rows": data,
            "row_count": len(rows),
            "truncated": len(rows) > req.limit,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sorgu hatasi: {e}") from e
