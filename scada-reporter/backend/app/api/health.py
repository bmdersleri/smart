"""Liveness and readiness endpoints.

GET /live  — always 200; no dependency check (used by process supervisors).
GET /ready — probes DB, Alembic head, and scheduler; 200 or 503.

Note: Redis is NOT probed here because this project uses no Redis client
(in-process cache only). If Redis is introduced later, add a probe then.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db_health import alembic_head_matches, db_ok
from app.services.scheduler import get_scheduler

router = APIRouter()


@router.get("/live")
async def liveness():
    """Liveness probe — always succeeds as long as the process is alive."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    """Readiness probe — checks DB connectivity, Alembic head, and scheduler.

    Returns 200 when all checks pass, 503 with per-check details otherwise.
    """
    db_result = await db_ok()
    alembic_result = await alembic_head_matches()
    if settings.RUN_SCHEDULER:
        sched = get_scheduler()
        scheduler_result: bool | str = sched is not None and getattr(sched, "running", False)
    else:
        scheduler_result = "disabled"

    checks = {
        "db": db_result,
        "alembic_head": alembic_result,
        "scheduler": scheduler_result,
    }

    scheduler_ok = scheduler_result == "disabled" or scheduler_result is True
    all_ok = db_result and alembic_result and scheduler_ok
    status_code = 200 if all_ok else 503
    body = {
        "status": "ready" if all_ok else "not_ready",
        "role": {
            "collector_enabled": settings.RUN_COLLECTOR,
            "scheduler_enabled": settings.RUN_SCHEDULER,
        },
        "checks": checks,
    }
    return JSONResponse(content=body, status_code=status_code)
