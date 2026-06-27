from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

_scheduler: AsyncIOScheduler | None = None
_RUNNING_RECENT_WINDOW = timedelta(minutes=5)
_LAST_RUN_ERROR_LIMIT = 4096


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _sync_db_url(async_url: str) -> str:
    return async_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    )


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_recently_running(scheduled_report, now: datetime) -> bool:
    if scheduled_report.last_run_status != "running" or scheduled_report.last_run_at is None:
        return False
    age = now - _normalize_utc(scheduled_report.last_run_at)
    return timedelta(0) <= age <= _RUNNING_RECENT_WINDOW


def _bound_last_run_error(message: str | None) -> str | None:
    if message is None or len(message) <= _LAST_RUN_ERROR_LIMIT:
        return message
    return message[:_LAST_RUN_ERROR_LIMIT]


async def start_scheduler(db_url: str) -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=_sync_db_url(db_url))},
        executors={"default": AsyncIOExecutor()},
    )
    _scheduler.start()
    await _sync_db_to_scheduler()

    from app.monitor.retention import prune_resolved_incidents

    _scheduler.add_job(
        prune_resolved_incidents,
        "cron",
        id="plc_incident_prune",
        hour=3,
        minute=30,
        replace_existing=True,
    )

    from app.core.config import settings

    if settings.RUN_BACKUP_SCHEDULER:
        m, h, dom, mon, dow = settings.BACKUP_SCHEDULE_CRON.split()
        _scheduler.add_job(
            scheduled_backup_job,
            "cron",
            id="db_backup",
            minute=m,
            hour=h,
            day=dom,
            month=mon,
            day_of_week=dow,
            replace_existing=True,
        )


async def scheduled_backup_job() -> None:
    """Nightly backup + retention prune. Opens its own session."""
    from app.api.backup import run_backup  # local import avoids router import cycle
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.models.backup import Backup
    from app.services import backup_engine as be

    async with AsyncSessionLocal() as db:
        await run_backup(db, trigger="scheduled", user_id=None)
        rows = list((await db.execute(select(Backup))).scalars().all())
        now_ts = datetime.now(UTC).timestamp()
        for bid in be.expired_backup_ids(
            rows, retention_days=settings.BACKUP_RETENTION_DAYS, now_ts=now_ts
        ):
            rec = await db.get(Backup, bid)
            if rec is None:
                continue
            if rec.path and os.path.exists(rec.path):
                os.remove(rec.path)
            await db.delete(rec)
        await db.commit()


async def register_job(scheduled) -> str:
    assert _scheduler is not None
    job_id = f"sr_{scheduled.id}"
    if scheduled.schedule_type == "cron":
        _scheduler.add_job(
            _run_scheduled_report,
            "cron",
            id=job_id,
            args=[scheduled.id],
            hour=scheduled.cron_hour,
            minute=scheduled.cron_minute or 0,
            day_of_week=scheduled.cron_day_of_week,
            day=scheduled.cron_day_of_month,
            replace_existing=True,
        )
    else:
        _scheduler.add_job(
            _run_scheduled_report,
            "interval",
            id=job_id,
            args=[scheduled.id],
            hours=scheduled.interval_hours,
            replace_existing=True,
        )
    return job_id


async def remove_job(job_id: str) -> None:
    if _scheduler and _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)


async def _sync_db_to_scheduler() -> None:
    """Re-register active ScheduledReport rows on startup (idempotent)."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.scheduled_report import ScheduledReport

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledReport).where(ScheduledReport.is_active.is_(True))
        )
        for sr in result.scalars().all():
            await register_job(sr)


async def _run_scheduled_report(scheduled_report_id: int) -> None:
    """APScheduler job function — owns its own DB session."""

    from app.core.database import AsyncSessionLocal
    from app.models.report_archive import ReportArchive
    from app.models.report_template import ReportTemplate
    from app.models.scheduled_report import ScheduledReport
    from app.services.report_generator import generate_report_from_template, resolve_time_range

    async with AsyncSessionLocal() as db:
        sr = await db.get(ScheduledReport, scheduled_report_id)
        if sr is None:
            return
        template = await db.get(ReportTemplate, sr.template_id)
        if template is None:
            return

        now = datetime.now(UTC)
        if _is_recently_running(sr, now):
            job = _scheduler.get_job(f"sr_{sr.id}") if _scheduler else None
            sr.next_run_at = job.next_run_time if job else None
            await db.commit()
            return

        sr.last_run_status = "running"
        sr.last_run_at = now
        await db.commit()

        archive = ReportArchive(
            template_id=template.id,
            scheduled_report_id=sr.id,
            status="pending",
            trigger="scheduled",
            tag_ids=template.tag_ids,
            start=datetime.now(UTC),  # will be overwritten by generator
            end=datetime.now(UTC),
            interval=template.interval,
            output_format=template.output_format,
        )
        db.add(archive)
        await db.commit()
        await db.refresh(archive)

        try:
            start, end = resolve_time_range(template)
            archive.start = start
            archive.end = end
            await db.commit()
            await generate_report_from_template(template, start, end, db, archive.id)
            sr.last_run_status = "completed"
            sr.last_run_error = None
        except Exception as exc:
            sr.last_run_status = "failed"
            sr.last_run_error = _bound_last_run_error(str(exc))

        job = _scheduler.get_job(f"sr_{sr.id}") if _scheduler else None
        sr.next_run_at = job.next_run_time if job else None
        await db.commit()
