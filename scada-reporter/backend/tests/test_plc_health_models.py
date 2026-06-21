import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident


@pytest.mark.asyncio
async def test_plc_health_row_roundtrip(db_session: AsyncSession):
    db_session.add(PlcHealth(plc_ip="10.0.0.1", plc_name="PLC1", rack=0, slot=1, connected=True))
    await db_session.commit()
    row = (await db_session.execute(select(PlcHealth))).scalar_one()
    assert row.plc_ip == "10.0.0.1"
    assert row.connected is True
    assert row.consecutive_fail == 0
    assert row.open_incident_count == 0


@pytest.mark.asyncio
async def test_plc_incident_open_query(db_session: AsyncSession):
    db_session.add(
        PlcIncident(
            plc_ip="10.0.0.1",
            plc_name="PLC1",
            rack=0,
            slot=1,
            kind="disconnected",
            severity="critical",
            message="down",
            detail={"reason": "timeout"},
        )
    )
    await db_session.commit()
    open_rows = (
        (await db_session.execute(select(PlcIncident).where(PlcIncident.resolved_at.is_(None))))
        .scalars()
        .all()
    )
    assert len(open_rows) == 1
    assert open_rows[0].detail == {"reason": "timeout"}
    assert open_rows[0].notified is False
