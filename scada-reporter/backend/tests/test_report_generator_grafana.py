import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.report_archive import ReportArchive
from app.models.report_template import ReportTemplate
from app.services.report_generator import generate_report_from_template


@pytest.mark.asyncio
async def test_generator_renders_panels_and_passes_to_pdf(db_session):
    tpl = ReportTemplate(
        name="gf",
        tag_ids="[]",
        output_format="pdf",
        show_summary_stats=False,
        show_trend_charts=False,
        show_anomaly_table=False,
        anomaly_enabled=False,
        grafana_panels=json.dumps([{"dashboard_uid": "d1", "panel_id": 1, "title": "Debi"}]),
    )
    db_session.add(tpl)
    await db_session.commit()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    archive = ReportArchive(
        template_id=tpl.id,
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=start,
        end=end,
        interval="hourly",
        output_format="pdf",
    )
    db_session.add(archive)
    await db_session.commit()

    captured = {}

    def fake_build_pdf(*args, **kwargs):
        captured["grafana_charts"] = kwargs.get("grafana_charts")
        return b"%PDF-1.4 fake"

    with (
        patch(
            "app.services.report_generator.render_panel",
            new=AsyncMock(return_value=b"PNGBYTES"),
        ),
        patch("app.services.report_generator.build_pdf", side_effect=fake_build_pdf),
    ):
        result = await generate_report_from_template(tpl, start, end, db_session, archive.id)

    assert result.status == "completed"
    assert captured["grafana_charts"][0]["title"] == "Debi"
    assert captured["grafana_charts"][0]["png"] == b"PNGBYTES"
    assert captured["grafana_charts"][0]["error"] is None


@pytest.mark.asyncio
async def test_generator_tolerates_render_failure(db_session):
    tpl = ReportTemplate(
        name="gf2",
        tag_ids="[]",
        output_format="pdf",
        show_summary_stats=False,
        show_trend_charts=False,
        show_anomaly_table=False,
        anomaly_enabled=False,
        grafana_panels=json.dumps([{"dashboard_uid": "d1", "panel_id": 1, "title": "Debi"}]),
    )
    db_session.add(tpl)
    await db_session.commit()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    archive = ReportArchive(
        template_id=tpl.id,
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=start,
        end=end,
        interval="hourly",
        output_format="pdf",
    )
    db_session.add(archive)
    await db_session.commit()

    captured = {}

    def fake_build_pdf(*args, **kwargs):
        captured["grafana_charts"] = kwargs.get("grafana_charts")
        return b"%PDF-1.4 fake"

    with (
        patch(
            "app.services.report_generator.render_panel",
            new=AsyncMock(return_value=b""),  # render başarısız
        ),
        patch("app.services.report_generator.build_pdf", side_effect=fake_build_pdf),
    ):
        result = await generate_report_from_template(tpl, start, end, db_session, archive.id)

    assert result.status == "completed"  # rapor düşmedi
    assert captured["grafana_charts"][0]["png"] == b""
    assert captured["grafana_charts"][0]["error"] is not None
