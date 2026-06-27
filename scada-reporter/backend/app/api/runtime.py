from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import require_role
from app.api.license_guard import require_writable
from app.models.user import User
from app.services.runtime_control import (
    runtime_status,
    start_collector,
    start_runtime_scheduler,
    stop_collector,
    stop_runtime_scheduler,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])


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


@router.get("/status", response_model=RuntimeStatus)
async def get_runtime_status(_: User = Depends(require_role("admin"))):
    return runtime_status()


@router.post("/collector/start", response_model=RuntimeStatus)
async def start_runtime_collector(
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await start_collector()
    return runtime_status()


@router.post("/collector/stop", response_model=RuntimeStatus)
async def stop_runtime_collector(
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await stop_collector()
    return runtime_status()


@router.post("/scheduler/start", response_model=RuntimeStatus)
async def start_scheduler_runtime(
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await start_runtime_scheduler()
    return runtime_status()


@router.post("/scheduler/stop", response_model=RuntimeStatus)
async def stop_scheduler_runtime(
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    stop_runtime_scheduler()
    return runtime_status()
