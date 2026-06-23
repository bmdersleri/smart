import asyncio
import contextlib
import json
import os
import re
from datetime import UTC, datetime
from math import ceil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_perm, require_role
from app.api.license_guard import require_feature
from app.core.database import get_db
from app.models.report_archive import ReportArchive
from app.models.report_template import ReportTemplate
from app.models.scheduled_report import ScheduledReport
from app.models.user import User
from app.services.report_generator import generate_report_from_template, resolve_time_range
from app.services.scheduler import get_scheduler, register_job, remove_job

router = APIRouter(
    prefix="/advanced-reports",
    tags=["advanced-reports"],
    dependencies=[Depends(require_feature("advanced_reports"))],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

# Strict allowlist for Grafana dashboard UIDs (alphanumeric, dash, underscore; max 64 chars).
_DASHBOARD_UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class GrafanaPanelRef(BaseModel):
    dashboard_uid: str
    panel_id: int
    title: str

    @field_validator("dashboard_uid")
    @classmethod
    def _validate_dashboard_uid(cls, v: str) -> str:
        if not _DASHBOARD_UID_RE.match(v):
            raise ValueError(
                "dashboard_uid must match ^[A-Za-z0-9_-]{1,64}$ "
                "(alphanumeric, dash, underscore; 1–64 chars)"
            )
        return v

    @field_validator("panel_id")
    @classmethod
    def _validate_panel_id(cls, v: int) -> int:
        if v < 0:
            raise ValueError("panel_id must be a non-negative integer")
        return v


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    tag_ids: list[int]
    time_range_type: str = "last_24h"
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    interval: str = "hourly"
    output_format: str = "excel"
    include_std_dev: bool = True
    include_percentiles: bool = True
    percentile_levels: list[int] = [10, 25, 50, 75, 90, 95]
    include_trend_line: bool = True
    anomaly_enabled: bool = True
    anomaly_zscore_threshold: float = 3.0
    show_summary_stats: bool = True
    show_trend_charts: bool = True
    show_anomaly_table: bool = True
    show_raw_data: bool = False
    grafana_panels: list[GrafanaPanelRef] = []


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str
    tag_ids: list[int]
    time_range_type: str
    custom_start: datetime | None
    custom_end: datetime | None
    interval: str
    output_format: str
    include_std_dev: bool
    include_percentiles: bool
    percentile_levels: list[int]
    include_trend_line: bool
    anomaly_enabled: bool
    anomaly_zscore_threshold: float
    show_summary_stats: bool
    show_trend_charts: bool
    show_anomaly_table: bool
    show_raw_data: bool
    grafana_panels: list[GrafanaPanelRef]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: ReportTemplate) -> TemplateResponse:
        data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        data["tag_ids"] = json.loads(obj.tag_ids)
        data["percentile_levels"] = json.loads(obj.percentile_levels)
        data["grafana_panels"] = json.loads(obj.grafana_panels)
        return cls(**data)


class ScheduledCreate(BaseModel):
    template_id: int
    name: str
    schedule_type: str
    cron_hour: int | None = None
    cron_minute: int | None = 0
    cron_day_of_week: str | None = None
    cron_day_of_month: int | None = None
    interval_hours: int | None = None


class ScheduledResponse(BaseModel):
    id: int
    template_id: int
    name: str
    schedule_type: str
    cron_hour: int | None
    cron_minute: int | None
    cron_day_of_week: str | None
    cron_day_of_month: int | None
    interval_hours: int | None
    apscheduler_job_id: str | None
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_error: str | None
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArchiveEntryResponse(BaseModel):
    id: int
    template_id: int | None
    scheduled_report_id: int | None
    status: str
    trigger: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    tag_ids: list[int]
    start: datetime
    end: datetime
    interval: str
    output_format: str
    file_path: str | None
    file_size_bytes: int | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: ReportArchive) -> ArchiveEntryResponse:
        data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        data["tag_ids"] = json.loads(obj.tag_ids)
        data.pop("result_json", None)
        return cls(**data)


class PaginatedArchiveResponse(BaseModel):
    items: list[ArchiveEntryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RunRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(ReportTemplate).order_by(ReportTemplate.created_at.desc()))
    return [TemplateResponse.from_orm(t) for t in result.scalars().all()]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("report_template:create")),
):
    tmpl = ReportTemplate(
        name=body.name,
        description=body.description,
        tag_ids=json.dumps(body.tag_ids),
        time_range_type=body.time_range_type,
        custom_start=body.custom_start,
        custom_end=body.custom_end,
        interval=body.interval,
        output_format=body.output_format,
        include_std_dev=body.include_std_dev,
        include_percentiles=body.include_percentiles,
        percentile_levels=json.dumps(body.percentile_levels),
        include_trend_line=body.include_trend_line,
        anomaly_enabled=body.anomaly_enabled,
        anomaly_zscore_threshold=body.anomaly_zscore_threshold,
        show_summary_stats=body.show_summary_stats,
        show_trend_charts=body.show_trend_charts,
        show_anomaly_table=body.show_anomaly_table,
        show_raw_data=body.show_raw_data,
        grafana_panels=json.dumps([p.model_dump() for p in body.grafana_panels]),
        created_by=user.id,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateResponse.from_orm(tmpl)


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    tmpl = await db.get(ReportTemplate, template_id)
    if not tmpl:
        raise HTTPException(404, "Şablon bulunamadı")
    return TemplateResponse.from_orm(tmpl)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("report_template:edit")),
):
    tmpl = await db.get(ReportTemplate, template_id)
    if not tmpl:
        raise HTTPException(404, "Şablon bulunamadı")
    tmpl.name = body.name
    tmpl.description = body.description
    tmpl.tag_ids = json.dumps(body.tag_ids)
    tmpl.time_range_type = body.time_range_type
    tmpl.custom_start = body.custom_start
    tmpl.custom_end = body.custom_end
    tmpl.interval = body.interval
    tmpl.output_format = body.output_format
    tmpl.include_std_dev = body.include_std_dev
    tmpl.include_percentiles = body.include_percentiles
    tmpl.percentile_levels = json.dumps(body.percentile_levels)
    tmpl.include_trend_line = body.include_trend_line
    tmpl.anomaly_enabled = body.anomaly_enabled
    tmpl.anomaly_zscore_threshold = body.anomaly_zscore_threshold
    tmpl.show_summary_stats = body.show_summary_stats
    tmpl.show_trend_charts = body.show_trend_charts
    tmpl.show_anomaly_table = body.show_anomaly_table
    tmpl.show_raw_data = body.show_raw_data
    tmpl.grafana_panels = json.dumps([p.model_dump() for p in body.grafana_panels])
    tmpl.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateResponse.from_orm(tmpl)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("report_template:delete")),
):
    tmpl = await db.get(ReportTemplate, template_id)
    if not tmpl:
        raise HTTPException(404, "Şablon bulunamadı")
    await db.delete(tmpl)
    await db.commit()


@router.post("/templates/{template_id}/run", response_model=ArchiveEntryResponse, status_code=202)
async def run_template(
    template_id: int,
    body: RunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    tmpl = await db.get(ReportTemplate, template_id)
    if not tmpl:
        raise HTTPException(404, "Şablon bulunamadı")

    if body.start and body.end:
        start, end = body.start, body.end
    else:
        start, end = resolve_time_range(tmpl)

    archive = ReportArchive(
        template_id=tmpl.id,
        status="pending",
        trigger="manual",
        tag_ids=tmpl.tag_ids,
        start=start,
        end=end,
        interval=tmpl.interval,
        output_format=tmpl.output_format,
        triggered_by=user.id,
    )
    db.add(archive)
    await db.commit()
    await db.refresh(archive)

    archive_id = archive.id
    lang = user.language

    async def _run():
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as bg_db:
            with contextlib.suppress(Exception):
                await generate_report_from_template(tmpl, start, end, bg_db, archive_id, lang=lang)

    background_tasks.add_task(asyncio.ensure_future, _run())

    return ArchiveEntryResponse.from_orm(archive)


# ---------------------------------------------------------------------------
# Scheduled
# ---------------------------------------------------------------------------


@router.get("/scheduled", response_model=list[ScheduledResponse])
async def list_scheduled(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(ScheduledReport).order_by(ScheduledReport.created_at.desc()))
    return [
        ScheduledResponse.model_validate(s, from_attributes=True) for s in result.scalars().all()
    ]


@router.post("/scheduled", response_model=ScheduledResponse, status_code=201)
async def create_scheduled(
    body: ScheduledCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    tmpl = await db.get(ReportTemplate, body.template_id)
    if not tmpl:
        raise HTTPException(404, "Şablon bulunamadı")

    sr = ScheduledReport(
        template_id=body.template_id,
        name=body.name,
        schedule_type=body.schedule_type,
        cron_hour=body.cron_hour,
        cron_minute=body.cron_minute,
        cron_day_of_week=body.cron_day_of_week,
        cron_day_of_month=body.cron_day_of_month,
        interval_hours=body.interval_hours,
        is_active=True,
    )
    db.add(sr)
    await db.commit()
    await db.refresh(sr)

    job_id = await register_job(sr)
    sr.apscheduler_job_id = job_id
    sched = get_scheduler()
    job = sched.get_job(job_id) if sched else None
    sr.next_run_at = job.next_run_time if job else None
    await db.commit()
    await db.refresh(sr)
    return ScheduledResponse.model_validate(sr, from_attributes=True)


@router.put("/scheduled/{scheduled_id}", response_model=ScheduledResponse)
async def update_scheduled(
    scheduled_id: int,
    body: ScheduledCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    sr = await db.get(ScheduledReport, scheduled_id)
    if not sr:
        raise HTTPException(404, "Zamanlanmış rapor bulunamadı")

    if sr.apscheduler_job_id:
        await remove_job(sr.apscheduler_job_id)

    sr.template_id = body.template_id
    sr.name = body.name
    sr.schedule_type = body.schedule_type
    sr.cron_hour = body.cron_hour
    sr.cron_minute = body.cron_minute
    sr.cron_day_of_week = body.cron_day_of_week
    sr.cron_day_of_month = body.cron_day_of_month
    sr.interval_hours = body.interval_hours
    await db.commit()

    if sr.is_active:
        job_id = await register_job(sr)
        sr.apscheduler_job_id = job_id
        sched = get_scheduler()
        job = sched.get_job(job_id) if sched else None
        sr.next_run_at = job.next_run_time if job else None
        await db.commit()

    await db.refresh(sr)
    return ScheduledResponse.model_validate(sr, from_attributes=True)


@router.delete("/scheduled/{scheduled_id}", status_code=204)
async def delete_scheduled(
    scheduled_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    sr = await db.get(ScheduledReport, scheduled_id)
    if not sr:
        raise HTTPException(404, "Zamanlanmış rapor bulunamadı")
    if sr.apscheduler_job_id:
        await remove_job(sr.apscheduler_job_id)
    await db.delete(sr)
    await db.commit()


@router.patch("/scheduled/{scheduled_id}/toggle", response_model=ScheduledResponse)
async def toggle_scheduled(
    scheduled_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    sr = await db.get(ScheduledReport, scheduled_id)
    if not sr:
        raise HTTPException(404, "Zamanlanmış rapor bulunamadı")

    sr.is_active = not sr.is_active
    if sr.is_active:
        job_id = await register_job(sr)
        sr.apscheduler_job_id = job_id
        sched = get_scheduler()
        job = sched.get_job(job_id) if sched else None
        sr.next_run_at = job.next_run_time if job else None
    else:
        if sr.apscheduler_job_id:
            await remove_job(sr.apscheduler_job_id)
        sr.next_run_at = None

    await db.commit()
    await db.refresh(sr)
    return ScheduledResponse.model_validate(sr, from_attributes=True)


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


@router.get("/archive", response_model=PaginatedArchiveResponse)
async def list_archive(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    template_id: int | None = Query(None),
    status: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(ReportArchive)
    if template_id is not None:
        q = q.where(ReportArchive.template_id == template_id)
    if status:
        q = q.where(ReportArchive.status == status)
    if date_from:
        q = q.where(ReportArchive.created_at >= date_from)
    if date_to:
        q = q.where(ReportArchive.created_at <= date_to)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(ReportArchive.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return PaginatedArchiveResponse(
        items=[ArchiveEntryResponse.from_orm(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.get("/archive/{archive_id}", response_model=ArchiveEntryResponse)
async def get_archive_entry(
    archive_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    entry = await db.get(ReportArchive, archive_id)
    if not entry:
        raise HTTPException(404, "Arşiv girişi bulunamadı")
    return ArchiveEntryResponse.from_orm(entry)


@router.get("/archive/{archive_id}/download")
async def download_archive(
    archive_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    entry = await db.get(ReportArchive, archive_id)
    if not entry:
        raise HTTPException(404, "Arşiv girişi bulunamadı")
    if entry.status != "completed" or not entry.file_path:
        raise HTTPException(400, f"Rapor henüz hazır değil (status={entry.status})")
    if not os.path.exists(entry.file_path):
        raise HTTPException(404, "Rapor dosyası bulunamadı (disk)")

    ext_to_mime = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "json": "application/json",
    }
    ext = entry.file_path.rsplit(".", 1)[-1].lower()
    media_type = ext_to_mime.get(ext, "application/octet-stream")
    filename = f"rapor_{archive_id}.{ext}"
    return FileResponse(entry.file_path, media_type=media_type, filename=filename)


@router.delete("/archive/{archive_id}", status_code=204)
async def delete_archive(
    archive_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    entry = await db.get(ReportArchive, archive_id)
    if not entry:
        raise HTTPException(404, "Arşiv girişi bulunamadı")
    if entry.file_path and os.path.exists(entry.file_path):
        with contextlib.suppress(OSError):
            os.unlink(entry.file_path)
    await db.delete(entry)
    await db.commit()
