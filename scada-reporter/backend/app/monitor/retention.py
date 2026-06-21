from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.plc_incident import PlcIncident


async def prune_resolved_incidents(
    sessionmaker=AsyncSessionLocal, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.PLC_INCIDENT_RETENTION_DAYS)
    async with sessionmaker() as db:
        result = await db.execute(
            delete(PlcIncident).where(
                PlcIncident.resolved_at.is_not(None), PlcIncident.resolved_at < cutoff
            )
        )
        await db.commit()
        return result.rowcount or 0
