"""Integration tests for report_generator — uses in-memory SQLite, no HTTP."""

import gzip
import itertools
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.models.report_archive import ReportArchive
from app.models.tag import Tag, TagReading
from app.services.report_generator import generate_report_from_template, resolve_time_range

_tag_counter = itertools.count(1)

# ---------------------------------------------------------------------------
# Fake template helpers
# ---------------------------------------------------------------------------


@dataclass
class _Template:
    tag_ids: str = "[1]"
    time_range_type: str = "last_24h"
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    interval: str = "hourly"
    output_format: str = "excel"
    percentile_levels: str = "[10,50,90]"
    include_std_dev: bool = True
    include_percentiles: bool = True
    include_trend_line: bool = True
    anomaly_enabled: bool = True
    anomaly_zscore_threshold: float = 3.0
    show_summary_stats: bool = True
    show_trend_charts: bool = True
    show_anomaly_table: bool = True
    show_raw_data: bool = False


async def _seed_tag_and_readings(db, n_readings: int = 60) -> Tag:
    uid = next(_tag_counter)
    tag = Tag(
        node_id=f"ns=2;s=IntegTestPump_{uid}",
        name=f"IntegTestPump_{uid}",
        unit="m3/h",
        device="PLC1",
        min_alarm=5.0,
        max_alarm=20.0,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    base = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    readings = []
    for i in range(n_readings):
        val = 10.0 + (15.0 if i == 30 else 0.0)  # spike at i=30
        readings.append(
            TagReading(
                tag_id=tag.id,
                value=val,
                quality=192,
                timestamp=base + timedelta(seconds=i * 60),
            )
        )
    db.add_all(readings)
    await db.commit()
    return tag


async def _make_archive(db, tag_id: int, fmt: str = "excel") -> ReportArchive:
    now = datetime.now(UTC)
    archive = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids=json.dumps([tag_id]),
        start=now - timedelta(hours=2),
        end=now,
        interval="hourly",
        output_format=fmt,
    )
    db.add(archive)
    await db.commit()
    await db.refresh(archive)
    return archive


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_time_range_last_24h():
    @dataclass
    class T:
        time_range_type: str = "last_24h"
        custom_start = None
        custom_end = None

    start, end = resolve_time_range(T())
    delta = end - start
    assert abs(delta.total_seconds() - 86400) < 2


@pytest.mark.asyncio
async def test_resolve_time_range_custom():
    s = datetime(2026, 6, 1, tzinfo=UTC)
    e = datetime(2026, 6, 10, tzinfo=UTC)

    @dataclass
    class T:
        time_range_type: str = "custom"
        custom_start: datetime = s
        custom_end: datetime = e

    start, end = resolve_time_range(T())
    assert start == s
    assert end == e


@pytest.mark.asyncio
async def test_generate_excel_report_completes(db_session):
    tag = await _seed_tag_and_readings(db_session, n_readings=60)
    template = _Template(tag_ids=json.dumps([tag.id]))
    archive = await _make_archive(db_session, tag.id, fmt="excel")

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 2, 0, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)

    assert result.status == "completed"
    assert result.file_path is not None
    assert result.file_path.endswith(".xlsx")
    assert result.file_size_bytes is not None and result.file_size_bytes > 0
    assert result.result_json is not None

    # result_json is valid gzip-compressed JSON
    summary = json.loads(gzip.decompress(result.result_json))
    assert "tags" in summary
    assert len(summary["tags"]) == 1
    assert summary["tags"][0]["name"].startswith("IntegTestPump")

    # File written to disk
    assert os.path.exists(result.file_path)
    os.unlink(result.file_path)


@pytest.mark.asyncio
async def test_generate_json_report_completes(db_session):
    tag = await _seed_tag_and_readings(db_session, n_readings=30)
    template = _Template(tag_ids=json.dumps([tag.id]), output_format="json")
    archive = await _make_archive(db_session, tag.id, fmt="json")

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 2, 0, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)

    assert result.status == "completed"
    assert result.file_path is not None and result.file_path.endswith(".json")
    with open(result.file_path, "rb") as f:
        data = json.loads(f.read())
    assert "tags" in data
    os.unlink(result.file_path)


@pytest.mark.asyncio
async def test_generate_pdf_report_completes(db_session):
    tag = await _seed_tag_and_readings(db_session, n_readings=24)
    template = _Template(tag_ids=json.dumps([tag.id]), output_format="pdf")
    archive = await _make_archive(db_session, tag.id, fmt="pdf")

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 1, 0, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)

    assert result.status == "completed"
    assert result.file_path is not None and result.file_path.endswith(".pdf")
    with open(result.file_path, "rb") as f:
        pdf_bytes = f.read()
    assert pdf_bytes[:4] == b"%PDF"
    os.unlink(result.file_path)


@pytest.mark.asyncio
async def test_archive_status_running_then_completed(db_session):
    """archive.status goes pending→completed; started_at and completed_at populated."""
    tag = await _seed_tag_and_readings(db_session, n_readings=10)
    template = _Template(tag_ids=json.dumps([tag.id]), show_trend_charts=False)
    archive = await _make_archive(db_session, tag.id)

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 1, 0, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)

    assert result.started_at is not None
    assert result.completed_at is not None
    assert result.completed_at >= result.started_at
    assert result.error_message is None
    if result.file_path and os.path.exists(result.file_path):
        os.unlink(result.file_path)


@pytest.mark.asyncio
async def test_empty_readings_produces_completed_report(db_session):
    """Tag with no readings in window → completed report with empty stats, no crash."""
    tag = Tag(
        node_id="ns=2;s=EmptyTag",
        name="EmptyTag",
        unit="bar",
        device="PLC1",
    )
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    template = _Template(tag_ids=json.dumps([tag.id]), show_trend_charts=False)
    archive = await _make_archive(db_session, tag.id)

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 1, 0, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)
    assert result.status == "completed"
    if result.file_path and os.path.exists(result.file_path):
        os.unlink(result.file_path)


@pytest.mark.asyncio
async def test_anomalies_detected_in_report_summary(db_session):
    """Spike at reading[30] triggers anomaly; result_json reflects it."""
    tag = await _seed_tag_and_readings(db_session, n_readings=60)
    template = _Template(
        tag_ids=json.dumps([tag.id]),
        anomaly_enabled=True,
        anomaly_zscore_threshold=2.0,
        show_trend_charts=False,
    )
    archive = await _make_archive(db_session, tag.id)

    start = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 15, 1, 30, 0, tzinfo=UTC)

    result = await generate_report_from_template(template, start, end, db_session, archive.id)
    assert result.status == "completed"

    summary = json.loads(gzip.decompress(result.result_json))
    anomaly_count = summary["tags"][0]["anomaly_count"]
    assert anomaly_count > 0, "Spike should produce at least one anomaly"

    if result.file_path and os.path.exists(result.file_path):
        os.unlink(result.file_path)
