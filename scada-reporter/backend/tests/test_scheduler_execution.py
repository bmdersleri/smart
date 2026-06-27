from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.core.database as database_mod
import app.services.scheduler as scheduler_mod
from app.models.report_archive import ReportArchive
from app.models.report_template import ReportTemplate
from app.models.scheduled_report import ScheduledReport


def _db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


async def _seed_scheduled_report(db_session, *, status: str | None = None, last_run_at=None):
    template = ReportTemplate(
        name=f"Scheduler Template {datetime.now(UTC).timestamp()}",
        tag_ids="[1]",
        interval="hourly",
        output_format="excel",
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    scheduled_report = ScheduledReport(
        template_id=template.id,
        name=f"Scheduler Report {datetime.now(UTC).timestamp()}",
        schedule_type="interval",
        interval_hours=1,
        is_active=True,
        last_run_status=status,
        last_run_at=last_run_at,
    )
    db_session.add(scheduled_report)
    await db_session.commit()
    await db_session.refresh(scheduled_report)
    return scheduled_report, template


@pytest.mark.asyncio
async def test_scheduler_skips_recent_overlap(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_mod, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        scheduler_mod,
        "_scheduler",
        SimpleNamespace(
            get_job=lambda _job_id: SimpleNamespace(
                next_run_time=datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
            )
        ),
    )
    generator = AsyncMock()
    monkeypatch.setattr("app.services.report_generator.generate_report_from_template", generator)
    monkeypatch.setattr("app.services.report_generator.resolve_time_range", AsyncMock())

    async with session_factory() as db_session:
        scheduled_report, _template = await _seed_scheduled_report(
            db_session,
            status="running",
            last_run_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    await scheduler_mod._run_scheduled_report(scheduled_report.id)

    generator.assert_not_awaited()
    async with session_factory() as db_session:
        sr = await db_session.get(ScheduledReport, scheduled_report.id)
        archives = (await db_session.execute(select(ReportArchive))).scalars().all()
        assert sr is not None
        assert sr.last_run_status == "running"
        assert len(archives) == 0
        assert _db_time(sr.next_run_at) == _db_time(datetime(2026, 6, 27, 12, 0, tzinfo=UTC))


@pytest.mark.asyncio
async def test_scheduler_bounds_failure_error(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_mod, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        scheduler_mod,
        "_scheduler",
        SimpleNamespace(get_job=lambda _job_id: SimpleNamespace(next_run_time=None)),
    )
    long_error = "failure-" + ("x" * 5000)

    async def _raise(*_args, **_kwargs):
        raise RuntimeError(long_error)

    monkeypatch.setattr("app.services.report_generator.generate_report_from_template", _raise)
    monkeypatch.setattr(
        "app.services.report_generator.resolve_time_range",
        lambda _template: (
            datetime(2026, 6, 27, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 27, 11, 0, tzinfo=UTC),
        ),
    )

    async with session_factory() as db_session:
        scheduled_report, _template = await _seed_scheduled_report(db_session)

    await scheduler_mod._run_scheduled_report(scheduled_report.id)

    async with session_factory() as db_session:
        sr = await db_session.get(ScheduledReport, scheduled_report.id)
        archives = (await db_session.execute(select(ReportArchive))).scalars().all()
        assert sr is not None
        assert sr.last_run_status == "failed"
        assert sr.last_run_error == long_error[:4096]
        assert len(archives) == 1


@pytest.mark.asyncio
async def test_scheduler_success_path_updates_status_and_archive(db_engine, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_mod, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        scheduler_mod,
        "_scheduler",
        SimpleNamespace(
            get_job=lambda _job_id: SimpleNamespace(
                next_run_time=datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
            )
        ),
    )
    generator = AsyncMock(return_value=SimpleNamespace(status="completed"))
    monkeypatch.setattr("app.services.report_generator.generate_report_from_template", generator)
    start = datetime(2026, 6, 27, 10, 0, tzinfo=UTC)
    end = datetime(2026, 6, 27, 11, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "app.services.report_generator.resolve_time_range",
        lambda _template: (start, end),
    )

    async with session_factory() as db_session:
        scheduled_report, _template = await _seed_scheduled_report(db_session)

    await scheduler_mod._run_scheduled_report(scheduled_report.id)

    generator.assert_awaited_once()
    async with session_factory() as db_session:
        sr = await db_session.get(ScheduledReport, scheduled_report.id)
        archive = (await db_session.execute(select(ReportArchive))).scalars().one()
        assert sr is not None
        assert sr.last_run_status == "completed"
        assert sr.last_run_error is None
        assert archive.scheduled_report_id == sr.id
        assert _db_time(archive.start) == _db_time(start)
        assert _db_time(archive.end) == _db_time(end)
