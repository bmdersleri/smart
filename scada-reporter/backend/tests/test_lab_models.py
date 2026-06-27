from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint


@pytest.mark.asyncio
async def test_sample_with_measurements_roundtrip(db_session):
    param = LabParameter(code="PH", name="pH", unit="", min_limit=6.5, max_limit=9.0)
    point = LabSamplePoint(code="INLET", name="Inlet")
    db_session.add_all([param, point])
    await db_session.flush()

    sample = LabSample(
        sample_point_id=point.id,
        sampled_at=datetime(2026, 6, 27, 9, 0, 0),
        entered_by=1,
        method="titration",
        batch_no="B1",
        note="",
    )
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=7.2))
    await db_session.commit()

    rows = (await db_session.execute(select(LabMeasurement))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == 7.2
    # defaults
    assert param.is_active is True
    assert param.approved is True
    assert param.mirror_to_tag_id is None


@pytest.mark.asyncio
async def test_deleting_sample_cascades_measurements(db_session):
    point = LabSamplePoint(code="OUT", name="Outlet")
    param = LabParameter(code="COD", name="COD", unit="mg/L")
    db_session.add_all([point, param])
    await db_session.flush()
    sample = LabSample(
        sample_point_id=point.id, sampled_at=datetime(2026, 6, 27, 9, 0), entered_by=1
    )
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=320.0))
    await db_session.commit()

    await db_session.delete(sample)
    await db_session.commit()
    rows = (await db_session.execute(select(LabMeasurement))).scalars().all()
    assert rows == []
