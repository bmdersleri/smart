from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.plc_incident import PlcIncident
from app.monitor.retention import prune_resolved_incidents


@pytest.mark.asyncio
async def test_prune_removes_old_resolved_keeps_open_and_recent(db_engine, db_session):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    now = datetime(2026, 6, 21, tzinfo=UTC)
    old = now - timedelta(days=200)
    recent = now - timedelta(days=5)
    db_session.add_all(
        [
            PlcIncident(
                plc_ip="1", kind="disconnected", severity="critical", message="o", resolved_at=old
            ),  # silinmeli
            PlcIncident(
                plc_ip="2",
                kind="disconnected",
                severity="critical",
                message="r",
                resolved_at=recent,
            ),  # kalmalı
            PlcIncident(
                plc_ip="3",
                kind="disconnected",
                severity="critical",
                message="open",
                resolved_at=None,
            ),  # açık, kalmalı
        ]
    )
    await db_session.commit()

    deleted = await prune_resolved_incidents(sessionmaker=sm, now=now)
    assert deleted == 1
    remaining = (await db_session.execute(select(PlcIncident))).scalars().all()
    assert len(remaining) == 2
