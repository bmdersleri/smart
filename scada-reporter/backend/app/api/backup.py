import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import authenticate_token, require_role
from app.api.license_guard import require_writable
from app.core import database
from app.core.config import settings
from app.core.database import get_db
from app.models.backup import Backup
from app.services import backup_engine as be
from app.services import backup_progress as bp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

# Strong refs to in-flight background jobs so the event loop doesn't GC them.
_tasks: set[asyncio.Task] = set()

# Map an engine phase to its (base, span) slice of the overall 0..1 progress bar.
# vacuum/compress dominate wall-clock on a large SQLite DB; compress is the only
# phase that reports a real byte fraction, so it gets the widest smooth span.
_CREATE_WEIGHTS: dict[str, tuple[float, float]] = {
    "vacuum": (0.0, 0.40),
    "dump": (0.0, 0.95),  # postgres single-shot pg_dump
    "verify": (0.40, 0.05),
    "compress": (0.45, 0.45),
    "hash": (0.90, 0.09),
    "done": (1.0, 0.0),
}


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _create_cb(key: str):
    def cb(phase: str, frac: float) -> None:
        base, span = _CREATE_WEIGHTS.get(phase, (-1.0, 0.0))
        if base < 0:
            return
        bp.update(key, phase=phase, fraction=base + frac * span)

    return cb


def _scaled_cb(key: str, label: str | None, base: float, span: float):
    """Wrap any engine cb into a sub-range [base, base+span] of the bar.

    `label` overrides the phase name (e.g. force all safety-snapshot phases to
    read 'safety'); pass None to let the engine's phase names through.
    """

    def cb(phase: str, frac: float) -> None:
        bp.update(key, phase=label or phase, fraction=base + frac * span)

    return cb


class BackupOut(BaseModel):
    id: int
    filename: str
    dialect: str
    kind: str
    status: str
    trigger: str
    size_bytes: int | None
    sha256: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "completed_at")
    def _ser_utc(self, v: datetime | None) -> str | None:
        # Stored naive-UTC; emit an explicit +00:00 offset so the frontend renders
        # local time correctly (matches the rest of the API's UTC-offset convention).
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


def _ts(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S")


async def _create_record(db: AsyncSession, *, trigger: str, user_id: int | None) -> Backup:
    rec = Backup(
        filename="",
        path="",
        dialect="",
        kind="full",
        status="running",
        trigger=trigger,
        triggered_by=user_id,
        created_at=datetime.now(UTC),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


def _apply_result(rec: Backup, res: dict) -> None:
    rec.filename = res["filename"]
    rec.path = res["path"]
    rec.dialect = res["dialect"]
    rec.size_bytes = res["size_bytes"]
    rec.sha256 = res["sha256"]
    rec.status = "verified"
    rec.completed_at = datetime.now(UTC)


async def run_backup(
    db: AsyncSession, *, trigger: str, user_id: int | None, progress_key: str | None = None
) -> Backup:
    """Create a snapshot inline (awaits to completion). Used by the scheduler and
    by the restore safety-snapshot; the manual API path runs it in the background
    instead so the request returns immediately."""
    rec = await _create_record(db, trigger=trigger, user_id=user_id)
    if progress_key:
        bp.start(progress_key)
    cb = _create_cb(progress_key) if progress_key else None
    try:
        res = await be.create_snapshot(
            dest_dir=settings.BACKUP_DIR,
            db_url=settings.DATABASE_URL,
            timestamp=f"{_ts(rec.created_at)}-{rec.id}",
            zstd_level=settings.BACKUP_ZSTD_LEVEL,
            progress_cb=cb,
        )
        _apply_result(rec, res)
    except Exception as exc:  # noqa: BLE001 — record failure, surface to caller
        rec.status = "failed"
        rec.error = str(exc)[:512]
        await db.commit()
        if progress_key:
            bp.finish(progress_key, error=rec.error)
        raise HTTPException(status_code=500, detail=f"Backup failed: {rec.error}") from exc
    await db.commit()
    await db.refresh(rec)
    if progress_key:
        bp.finish(progress_key)
    return rec


async def _run_create_job(backup_id: int) -> None:
    """Background worker: fill an already-created 'running' backup record."""
    key = str(backup_id)
    async with database.AsyncSessionLocal() as db:
        rec = await db.get(Backup, backup_id)
        if rec is None:
            bp.finish(key, error="backup record vanished")
            return
        try:
            res = await be.create_snapshot(
                dest_dir=settings.BACKUP_DIR,
                db_url=settings.DATABASE_URL,
                timestamp=f"{_ts(rec.created_at)}-{rec.id}",
                zstd_level=settings.BACKUP_ZSTD_LEVEL,
                progress_cb=_create_cb(key),
            )
            _apply_result(rec, res)
            await db.commit()
            bp.finish(key)
        except Exception as exc:  # noqa: BLE001 — background task: never raise
            rec.status = "failed"
            rec.error = str(exc)[:512]
            await db.commit()
            bp.finish(key, error=rec.error)
            logger.exception("backup %s failed", backup_id)


@router.post("", response_model=BackupOut, status_code=202)
async def create_backup(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> Backup:
    """Kick off a backup in the background. Returns the 'running' record
    immediately; subscribe to GET /backup/{id}/progress for live progress."""
    rec = await _create_record(db, trigger="manual", user_id=getattr(user, "id", None))
    bp.start(str(rec.id))
    _spawn(_run_create_job(rec.id))
    return rec


@router.get("", response_model=list[BackupOut])
async def list_backups(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
) -> list[Backup]:
    rows = (await db.execute(select(Backup).order_by(Backup.created_at.desc()))).scalars().all()
    return list(rows)


async def _progress_stream(key: str) -> AsyncGenerator[str]:
    """Emit the job's progress until it reaches a terminal state, then close."""
    while True:
        prog = bp.get(key)
        if prog is None:
            yield 'data: {"status": "unknown"}\n\n'
            return
        yield f"data: {json.dumps(prog)}\n\n"
        if prog["status"] in ("done", "failed"):
            return
        await asyncio.sleep(0.5)


async def _authorize_sse_admin(token: str, db: AsyncSession) -> None:
    user = await authenticate_token(token, db, sse_allowed=True)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Yetki yok")


@router.get("/{backup_id}/progress")
async def backup_progress(
    backup_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _authorize_sse_admin(token, db)
    return StreamingResponse(
        _progress_stream(str(backup_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{backup_id}/restore-progress")
async def restore_progress(
    backup_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _authorize_sse_admin(token, db)
    return StreamingResponse(
        _progress_stream(f"restore-{backup_id}"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
) -> FileResponse:
    rec = await db.get(Backup, backup_id)
    if rec is None or not rec.path or not os.path.exists(rec.path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(rec.path, filename=rec.filename, media_type="application/octet-stream")


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    rec = await db.get(Backup, backup_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.path and os.path.exists(rec.path):
        os.remove(rec.path)
    await db.delete(rec)
    await db.commit()
    bp.clear(str(backup_id))
    return {"deleted": backup_id}


class RestoreRequest(BaseModel):
    confirm: str


async def _run_restore_job(backup_id: int, user_id: int | None) -> None:
    """Background worker: safety-snapshot the current DB, then restore the chosen
    backup over it. Reports progress under the 'restore-{id}' key."""
    key = f"restore-{backup_id}"
    async with database.AsyncSessionLocal() as db:
        rec = await db.get(Backup, backup_id)
        if rec is None or not rec.path or not os.path.exists(rec.path):
            bp.finish(key, error="backup file not found")
            return
        try:
            # Safety snapshot of the CURRENT state before overwriting (0..50%).
            bp.update(key, phase="safety", fraction=0.0)
            safety = await _create_record(db, trigger="manual", user_id=user_id)
            res = await be.create_snapshot(
                dest_dir=settings.BACKUP_DIR,
                db_url=settings.DATABASE_URL,
                timestamp=f"{_ts(safety.created_at)}-{safety.id}",
                zstd_level=settings.BACKUP_ZSTD_LEVEL,
                progress_cb=_scaled_cb(key, "safety", 0.0, 0.5),
            )
            _apply_result(safety, res)
            await db.commit()
            # Restore over the live DB (50..100%).
            await asyncio.to_thread(
                be.restore_snapshot,
                backup_path=rec.path,
                db_url=settings.DATABASE_URL,
                progress_cb=_scaled_cb(key, None, 0.5, 0.5),
            )
            # Dispose pool so stale connections don't serve a mix of old/new pages.
            await database.engine.dispose()
            bp.finish(key)
        except Exception as exc:  # noqa: BLE001 — background task: never raise
            bp.finish(key, error=str(exc))
            logger.exception("restore of backup %s failed", backup_id)


@router.post("/{backup_id}/restore", status_code=202)
async def restore_backup(
    backup_id: int,
    body: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    if body.confirm != "RESTORE":
        raise HTTPException(status_code=400, detail="Confirmation token must be 'RESTORE'")
    rec = await db.get(Backup, backup_id)
    if rec is None or not rec.path or not os.path.exists(rec.path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    key = f"restore-{backup_id}"
    bp.start(key)
    _spawn(_run_restore_job(backup_id, getattr(user, "id", None)))
    return {
        "restoring": backup_id,
        "progress_key": key,
        "note": (
            "Restore started. Watch GET /backup/{id}/restore-progress. When it"
            " completes, restart the backend so all connections use the restored DB."
        ),
    }
