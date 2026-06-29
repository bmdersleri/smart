"""report_archive stores resolved facility-variable refs; orchestrator renders variables."""

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.models.report_archive import ReportArchive


@dataclass
class _VarTemplate:
    tag_ids: str = "[]"
    variable_ids: str = "[]"
    time_range_type: str = "custom"
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    interval: str = "daily"
    output_format: str = "json"
    percentile_levels: str = "[50]"
    include_std_dev: bool = True
    include_percentiles: bool = True
    include_trend_line: bool = False
    anomaly_enabled: bool = False
    anomaly_zscore_threshold: float = 3.0
    show_summary_stats: bool = True
    show_trend_charts: bool = False
    show_anomaly_table: bool = False
    show_raw_data: bool = False
    grafana_panels: str = "[]"


async def _make_scalar_var(db, version=2):
    from app.models.facility_variable import FacilityVariable
    from app.models.tag import Tag, TagReading

    tag = Tag(node_id="ns=2;s=VG", name="VG", unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    db.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 20), value=70.0))
    await db.commit()
    var = FacilityVariable(
        code="var_orch",
        name="Orch Var",
        kind="scalar",
        unit="m3",
        version=version,
        default_time_grain="day",
        expression_json=json.dumps(
            {
                "op": "reduce",
                "reduce": "sum",
                "source": {
                    "op": "series",
                    "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta",
                    "grain": "day",
                    "window": "day",
                },
            }
        ),
    )
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


@pytest.mark.asyncio
async def test_orchestrator_stamps_variable_refs(db_session):
    from app.services.report_generator import generate_report_from_template

    var = await _make_scalar_var(db_session, version=7)
    arch = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC),
        end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily",
        output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)

    tmpl = _VarTemplate(
        variable_ids=json.dumps([var.id]),
        custom_start=datetime(2026, 6, 1, tzinfo=UTC),
        custom_end=datetime(2026, 6, 2, tzinfo=UTC),
    )
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id, lang="tr"
    )
    await db_session.refresh(arch)
    assert arch.status == "completed"
    refs = json.loads(arch.variable_refs_json)
    assert refs[0]["variable_id"] == var.id
    assert refs[0]["version"] == 7
    # compressed summary carries the variable values
    summary = json.loads(gzip.decompress(arch.result_json))
    assert summary["variables"][0]["code"] == "var_orch"
    assert summary["variables"][0]["value"] == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_json_output_file_includes_variables(db_session, tmp_path, monkeypatch):
    from app.services.report_generator import generate_report_from_template

    monkeypatch.chdir(tmp_path)
    var = await _make_scalar_var(db_session)
    arch = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC),
        end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily",
        output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    tmpl = _VarTemplate(variable_ids=json.dumps([var.id]))
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id
    )
    await db_session.refresh(arch)
    with open(arch.file_path) as f:
        payload = json.load(f)
    assert payload["variables"][0]["code"] == "var_orch"


@pytest.mark.asyncio
async def test_archive_has_variable_refs_column(db_session):
    arch = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC),
        end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily",
        output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    assert arch.variable_refs_json is None
    arch.variable_refs_json = json.dumps([{"variable_id": 1, "code": "x", "version": 1}])
    await db_session.commit()
    await db_session.refresh(arch)
    assert json.loads(arch.variable_refs_json)[0]["code"] == "x"
