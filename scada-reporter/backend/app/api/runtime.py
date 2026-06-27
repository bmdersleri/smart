from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.api.license_guard import require_writable
from app.core.audit import record_audit
from app.core.database import get_db
from app.models.user import User
from app.services.runtime_control import (
    runtime_status,
    start_collector,
    start_runtime_scheduler,
    stop_collector,
    stop_runtime_scheduler,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])
RuntimeTarget = Literal["collector", "scheduler"]


class CollectorStatus(BaseModel):
    configured: bool
    running: bool
    poller_running: bool
    opcua_running: bool
    monitor_running: bool


class SchedulerStatus(BaseModel):
    configured: bool
    running: bool


class BackendStatus(BaseModel):
    status: str
    uptime_seconds: float
    started_at: str


class RuntimeStatus(BaseModel):
    controls_enabled: bool
    backend: BackendStatus
    collector: CollectorStatus
    scheduler: SchedulerStatus


async def _record_runtime_audit(
    db: AsyncSession,
    request: Request,
    actor: User,
    *,
    component: RuntimeTarget,
    action: str,
    before_running: bool,
    after_running: bool,
) -> None:
    await record_audit(
        db,
        actor=actor,
        action=f"runtime.{component}.{action}",
        target_type="runtime_component",
        target_id=component,
        detail={
            "component": component,
            "action": action,
            "before_running": before_running,
            "after_running": after_running,
        },
        ip=request.client.host if request.client else None,
    )


@router.get("/status", response_model=RuntimeStatus)
async def get_runtime_status(_: User = Depends(require_role("admin"))):
    return runtime_status()


@router.post("/collector/start", response_model=RuntimeStatus)
async def start_runtime_collector(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    before = runtime_status()
    await start_collector()
    after = runtime_status()
    await _record_runtime_audit(
        db,
        request,
        actor,
        component="collector",
        action="start",
        before_running=before["collector"]["running"],
        after_running=after["collector"]["running"],
    )
    await db.commit()
    return after


@router.post("/collector/stop", response_model=RuntimeStatus)
async def stop_runtime_collector(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    before = runtime_status()
    await stop_collector()
    after = runtime_status()
    await _record_runtime_audit(
        db,
        request,
        actor,
        component="collector",
        action="stop",
        before_running=before["collector"]["running"],
        after_running=after["collector"]["running"],
    )
    await db.commit()
    return after


@router.post("/scheduler/start", response_model=RuntimeStatus)
async def start_scheduler_runtime(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    before = runtime_status()
    await start_runtime_scheduler()
    after = runtime_status()
    await _record_runtime_audit(
        db,
        request,
        actor,
        component="scheduler",
        action="start",
        before_running=before["scheduler"]["running"],
        after_running=after["scheduler"]["running"],
    )
    await db.commit()
    return after


@router.post("/scheduler/stop", response_model=RuntimeStatus)
async def stop_scheduler_runtime(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    before = runtime_status()
    stop_runtime_scheduler()
    after = runtime_status()
    await _record_runtime_audit(
        db,
        request,
        actor,
        component="scheduler",
        action="stop",
        before_running=before["scheduler"]["running"],
        after_running=after["scheduler"]["running"],
    )
    await db.commit()
    return after
