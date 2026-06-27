"""Admin-only endpoint to read the audit log."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])

_MAX_LIMIT = 200


class AuditOut(BaseModel):
    id: int
    timestamp: datetime
    actor_user_id: int | None
    actor_username: str
    action: str
    target_type: str
    target_id: str | None
    detail: dict | None
    ip: str | None

    model_config = {"from_attributes": True}


def _to_out(row: AuditLog) -> AuditOut:
    detail: dict | None = None
    if row.detail is not None:
        try:
            detail = json.loads(row.detail)
        except ValueError, TypeError:
            detail = None
    return AuditOut(
        id=row.id,
        timestamp=row.timestamp,
        actor_user_id=row.actor_user_id,
        actor_username=row.actor_username,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        detail=detail,
        ip=row.ip,
    )


@router.get("/", response_model=list[AuditOut])
async def list_audit_log(
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[AuditOut]:
    """Return audit log rows newest-first.  Admin-only."""
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_to_out(row) for row in result.scalars().all()]
