import json

import pytest
from sqlalchemy import select

from app.models.report_template import ReportTemplate


@pytest.mark.asyncio
async def test_grafana_panels_defaults_to_empty_list(db_session):
    tpl = ReportTemplate(name="t1", tag_ids="[1]")
    db_session.add(tpl)
    await db_session.commit()
    row = await db_session.scalar(select(ReportTemplate).where(ReportTemplate.name == "t1"))
    assert json.loads(row.grafana_panels) == []


@pytest.mark.asyncio
async def test_grafana_panels_round_trips_json(db_session):
    panels = [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}]
    tpl = ReportTemplate(name="t2", tag_ids="[1]", grafana_panels=json.dumps(panels))
    db_session.add(tpl)
    await db_session.commit()
    row = await db_session.scalar(select(ReportTemplate).where(ReportTemplate.name == "t2"))
    assert json.loads(row.grafana_panels) == panels
