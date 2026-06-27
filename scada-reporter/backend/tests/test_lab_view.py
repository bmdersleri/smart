from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint

_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_lab_timeseries AS
SELECT ls.sampled_at AS time, sp.code AS point_code, lp.code AS param_code,
       lp.name AS param_name, lp.unit AS unit, lm.value AS value,
       lp.min_limit AS min_limit, lp.max_limit AS max_limit
FROM lab_measurements lm
JOIN lab_samples ls ON ls.id = lm.sample_id
JOIN lab_parameters lp ON lp.id = lm.parameter_id
JOIN lab_sample_points sp ON sp.id = ls.sample_point_id
WHERE lm.value IS NOT NULL
"""


@pytest.mark.asyncio
async def test_view_returns_flattened_timeseries(db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH", unit="", max_limit=9.0)
    db_session.add_all([point, param])
    await db_session.flush()
    sample = LabSample(
        sample_point_id=point.id, sampled_at=datetime(2026, 6, 27, 9, 0), entered_by=1
    )
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=7.2))
    await db_session.commit()

    await db_session.execute(text(_VIEW_SQL))
    rows = (
        await db_session.execute(
            text("SELECT point_code, param_code, value, max_limit FROM v_lab_timeseries")
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].point_code == "INLET"
    assert rows[0].param_code == "PH"
    assert rows[0].value == 7.2
    assert rows[0].max_limit == 9.0
