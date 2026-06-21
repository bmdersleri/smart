# tests/test_plc_monitor.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
from app.monitor import monitor
from app.monitor.detector import (
    EvalResult,
    OpenIncident,
    PlcMonitorState,
    PlcObservation,
)

KEY = ("10.0.0.1", 0, 1)


def _obs(connected=False, good=0, bad=0):
    return PlcObservation(
        key=KEY,
        name="PLC1",
        connected=connected,
        good_count=good,
        bad_count=bad,
        seconds_since_success=99.0,
        reconnects_in_window=0,
    )


@pytest.fixture
def _no_notify(monkeypatch):
    async def _noop(payload):
        return None

    monkeypatch.setattr(monitor.notifier, "dispatch", _noop)


@pytest.mark.asyncio
async def test_apply_result_opens_incident_and_upserts_health(
    db_engine, db_session: AsyncSession, _no_notify
):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    inc = OpenIncident(
        kind="disconnected", severity="critical", opened_at_mono=1.0, detail={"x": 1}
    )
    result = EvalResult(
        state=PlcMonitorState(open={"disconnected": inc}), opened=[inc], resolved=[]
    )
    await monitor.apply_result(_obs(), result, sessionmaker=sm)

    incidents = (await db_session.execute(select(PlcIncident))).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].kind == "disconnected"
    assert incidents[0].resolved_at is None

    health = (await db_session.execute(select(PlcHealth))).scalar_one()
    assert health.plc_ip == "10.0.0.1"
    assert health.open_incident_count == 1


@pytest.mark.asyncio
async def test_apply_result_resolves_open_incident(db_engine, db_session: AsyncSession, _no_notify):
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    # önce aç
    inc = OpenIncident(kind="disconnected", severity="critical", opened_at_mono=1.0, detail={})
    await monitor.apply_result(
        _obs(), EvalResult(PlcMonitorState(open={"disconnected": inc}), [inc], []), sessionmaker=sm
    )
    # sonra çöz
    await monitor.apply_result(
        _obs(connected=True, good=5),
        EvalResult(PlcMonitorState(open={}), [], ["disconnected"]),
        sessionmaker=sm,
    )
    row = (await db_session.execute(select(PlcIncident))).scalar_one()
    assert row.resolved_at is not None
