import asyncio
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.api.license_guard import require_writable
from app.core.config import settings
from app.core.database import get_db
from app.models.backup import Backup
from app.services import backup_engine as be

router = APIRouter(prefix="/backup", tags=["backup"])


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


def _ts(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S")


async def run_backup(db: AsyncSession, *, trigger: str, user_id: int | None) -> Backup:
    """Create a snapshot, persist metadata. Shared by API + scheduler."""
    now = datetime.now(UTC)
    rec = Backup(
        filename="",
        path="",
        dialect="",
        kind="full",
        status="running",
        trigger=trigger,
        triggered_by=user_id,
        created_at=now,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    try:
        res = await be.create_snapshot(
            dest_dir=settings.BACKUP_DIR, db_url=settings.DATABASE_URL, timestamp=_ts(now)
        )
        rec.filename = res["filename"]
        rec.path = res["path"]
        rec.dialect = res["dialect"]
        rec.size_bytes = res["size_bytes"]
        rec.sha256 = res["sha256"]
        rec.status = "verified"
        rec.completed_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001 — record failure, surface to caller
        rec.status = "failed"
        rec.error = str(exc)[:512]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Backup failed: {rec.error}") from exc
    await db.commit()
    await db.refresh(rec)
    return rec


@router.post("", response_model=BackupOut)
async def create_backup(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> Backup:
    return await run_backup(db, trigger="manual", user_id=getattr(user, "id", None))


@router.get("", response_model=list[BackupOut])
async def list_backups(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
) -> list[Backup]:
    rows = (await db.execute(select(Backup).order_by(Backup.created_at.desc()))).scalars().all()
    return list(rows)


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
    return {"deleted": backup_id}


class RestoreRequest(BaseModel):
    confirm: str


@router.post("/{backup_id}/restore")
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
    # safety snapshot of the CURRENT state before overwriting
    await run_backup(db, trigger="manual", user_id=getattr(user, "id", None))
    try:
        await asyncio.to_thread(
            be.restore_snapshot, backup_path=rec.path, db_url=settings.DATABASE_URL
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"restored": backup_id}
