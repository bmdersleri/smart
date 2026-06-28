"""Compliance Center API — permits, evaluation, events, notes, status.

Phase-1 backend slice. RBAC mirrors the rest of the app:
- read endpoints (overview/permits/events): any authenticated user
- permit creation: admin only
- evaluate / notes / status transitions: operator or admin (writable)

Audit rows are written via ``record_audit`` inside the endpoint transaction.
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.audit import record_audit
from app.core.database import get_db
from app.models.compliance import (
    EVENT_STATUSES,
    REPORT_FREQUENCIES,
    ComplianceEvent,
    ComplianceEventNote,
    CompliancePermit,
)
from app.models.user import User
from app.services import compliance_engine

router = APIRouter(prefix="/compliance", tags=["compliance"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class PermitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    facility_name: str = ""
    authority: str = ""
    permit_number: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    report_frequency: str = "monthly"
    report_cron: str | None = None
    is_active: bool = True


class PermitResponse(BaseModel):
    id: int
    name: str
    facility_name: str
    authority: str
    permit_number: str
    valid_from: datetime | None
    valid_to: datetime | None
    report_frequency: str
    report_cron: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: int
    permit_id: int
    parameter_id: int
    limit_id: int
    event_type: str
    severity: str
    period_start: datetime
    period_end: datetime
    observed_value: float | None
    limit_value: float | None
    status: str
    event_key: str
    evidence: dict | None
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: int | None
    resolved_at: datetime | None
    resolved_by: int | None
    waived_at: datetime | None
    waived_by: int | None
    waive_reason: str | None
    note_count: int = 0


class EventListResponse(BaseModel):
    total: int
    items: list[EventResponse]


class NoteCreate(BaseModel):
    note: str = Field(min_length=1)


class NoteResponse(BaseModel):
    id: int
    event_id: int
    user_id: int
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: str
    waive_reason: str | None = None


class EvaluateRequest(BaseModel):
    permit_id: int
    start: datetime
    end: datetime


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _event_to_response(event: ComplianceEvent, note_count: int = 0) -> EventResponse:
    try:
        evidence = json.loads(event.evidence_json) if event.evidence_json else None
    except ValueError, TypeError:
        evidence = None
    return EventResponse(
        id=event.id,
        permit_id=event.permit_id,
        parameter_id=event.parameter_id,
        limit_id=event.limit_id,
        event_type=event.event_type,
        severity=event.severity,
        period_start=event.period_start,
        period_end=event.period_end,
        observed_value=event.observed_value,
        limit_value=event.limit_value,
        status=event.status,
        event_key=event.event_key,
        evidence=evidence,
        created_at=event.created_at,
        updated_at=event.updated_at,
        acknowledged_at=event.acknowledged_at,
        acknowledged_by=event.acknowledged_by,
        resolved_at=event.resolved_at,
        resolved_by=event.resolved_by,
        waived_at=event.waived_at,
        waived_by=event.waived_by,
        waive_reason=event.waive_reason,
        note_count=note_count,
    )


async def _note_counts(db: AsyncSession, event_ids: list[int]) -> dict[int, int]:
    if not event_ids:
        return {}
    rows = (
        await db.execute(
            select(ComplianceEventNote.event_id, func.count())
            .where(ComplianceEventNote.event_id.in_(event_ids))
            .group_by(ComplianceEventNote.event_id)
        )
    ).all()
    return {event_id: count for event_id, count in rows}


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    active_permits = (
        await db.execute(
            select(func.count()).select_from(CompliancePermit).where(CompliancePermit.is_active)
        )
    ).scalar_one()
    open_events = (
        await db.execute(
            select(func.count())
            .select_from(ComplianceEvent)
            .where(ComplianceEvent.status == "open")
        )
    ).scalar_one()
    by_type_rows = (
        await db.execute(
            select(ComplianceEvent.event_type, func.count())
            .where(ComplianceEvent.status == "open")
            .group_by(ComplianceEvent.event_type)
        )
    ).all()
    by_event_type = {event_type: count for event_type, count in by_type_rows}
    return {
        "active_permits": int(active_permits),
        "open_events": int(open_events),
        "by_event_type": by_event_type,
        "missing_samples": int(by_event_type.get("missing_sample", 0)),
        "unresolved_explanations": int(by_event_type.get("needs_explanation", 0)),
        "packs_waiting": 0,
    }


# --------------------------------------------------------------------------
# Permits
# --------------------------------------------------------------------------


@router.get("/permits", response_model=list[PermitResponse])
async def list_permits(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CompliancePermit]:
    stmt = select(CompliancePermit).order_by(CompliancePermit.id.desc())
    if is_active is not None:
        stmt = stmt.where(CompliancePermit.is_active == is_active)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/permits", response_model=PermitResponse, status_code=201)
async def create_permit(
    data: PermitCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> CompliancePermit:
    if data.report_frequency not in REPORT_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"report_frequency must be one of {REPORT_FREQUENCIES}",
        )
    if data.report_frequency == "custom_cron" and not data.report_cron:
        raise HTTPException(
            status_code=422,
            detail="report_cron is required when report_frequency is custom_cron",
        )

    permit = CompliancePermit(
        name=data.name,
        facility_name=data.facility_name,
        authority=data.authority,
        permit_number=data.permit_number,
        valid_from=data.valid_from.replace(tzinfo=None) if data.valid_from else None,
        valid_to=data.valid_to.replace(tzinfo=None) if data.valid_to else None,
        report_frequency=data.report_frequency,
        report_cron=data.report_cron,
        is_active=data.is_active,
    )
    db.add(permit)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="compliance.permit.create",
        target_type="compliance_permit",
        target_id=permit.id,
        detail={"name": permit.name, "report_frequency": permit.report_frequency},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(permit)
    return permit


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


@router.post("/evaluate")
async def evaluate(
    data: EvaluateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
) -> dict:
    permit = await db.get(CompliancePermit, data.permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    result = await compliance_engine.evaluate_permit(db, data.permit_id, data.start, data.end)
    await record_audit(
        db,
        actor=user,
        action="compliance.evaluate",
        target_type="compliance_permit",
        target_id=data.permit_id,
        detail={
            "start": data.start.replace(tzinfo=None).isoformat(),
            "end": data.end.replace(tzinfo=None).isoformat(),
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
        },
        ip=_client_ip(request),
    )
    await db.commit()
    return result


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


@router.get("/events", response_model=EventListResponse)
async def list_events(
    permit_id: int | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EventListResponse:
    filters = []
    if permit_id is not None:
        filters.append(ComplianceEvent.permit_id == permit_id)
    if status is not None:
        filters.append(ComplianceEvent.status == status)
    if start is not None:
        filters.append(ComplianceEvent.period_start >= start.replace(tzinfo=None))
    if end is not None:
        filters.append(ComplianceEvent.period_end <= end.replace(tzinfo=None))

    total = (
        await db.execute(select(func.count()).select_from(ComplianceEvent).where(*filters))
    ).scalar_one()

    rows = list(
        (
            await db.execute(
                select(ComplianceEvent)
                .where(*filters)
                .order_by(ComplianceEvent.period_start.desc(), ComplianceEvent.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    counts = await _note_counts(db, [row.id for row in rows])
    return EventListResponse(
        total=int(total),
        items=[_event_to_response(row, counts.get(row.id, 0)) for row in rows],
    )


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EventResponse:
    event = await db.get(ComplianceEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Olay bulunamadı")
    counts = await _note_counts(db, [event.id])
    return _event_to_response(event, counts.get(event.id, 0))


@router.post("/events/{event_id}/notes", response_model=NoteResponse, status_code=201)
async def add_note(
    event_id: int,
    data: NoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
) -> ComplianceEventNote:
    event = await db.get(ComplianceEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Olay bulunamadı")

    existing = (
        await db.execute(
            select(func.count())
            .select_from(ComplianceEventNote)
            .where(ComplianceEventNote.event_id == event_id)
        )
    ).scalar_one()
    is_first_note = existing == 0

    note = ComplianceEventNote(event_id=event_id, user_id=user.id, note=data.note)
    db.add(note)

    # Adding the FIRST note to a source event auto-resolves any related open
    # needs_explanation event for the same parameter/limit/period.
    if is_first_note and event.event_type != "needs_explanation":
        related = (
            (
                await db.execute(
                    select(ComplianceEvent).where(
                        ComplianceEvent.permit_id == event.permit_id,
                        ComplianceEvent.parameter_id == event.parameter_id,
                        ComplianceEvent.limit_id == event.limit_id,
                        ComplianceEvent.period_start == event.period_start,
                        ComplianceEvent.period_end == event.period_end,
                        ComplianceEvent.event_type == "needs_explanation",
                        ComplianceEvent.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        for needs_event in related:
            needs_event.status = "resolved"
            needs_event.resolved_at = now
            needs_event.resolved_by = user.id
            needs_event.updated_at = now

    await record_audit(
        db,
        actor=user,
        action="compliance.event.note",
        target_type="compliance_event",
        target_id=event_id,
        detail={"event_type": event.event_type, "first_note": is_first_note},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(note)
    return note


@router.patch("/events/{event_id}/status", response_model=EventResponse)
async def update_status(
    event_id: int,
    data: StatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
) -> EventResponse:
    if data.status not in EVENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {EVENT_STATUSES}")

    event = await db.get(ComplianceEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Olay bulunamadı")

    now = datetime.utcnow()
    if data.status == "acknowledged":
        event.acknowledged_at = now
        event.acknowledged_by = user.id
    elif data.status == "resolved":
        event.resolved_at = now
        event.resolved_by = user.id
    elif data.status == "waived":
        if not data.waive_reason or not data.waive_reason.strip():
            raise HTTPException(
                status_code=422, detail="waive_reason is required to waive an event"
            )
        event.waived_at = now
        event.waived_by = user.id
        event.waive_reason = data.waive_reason

    event.status = data.status
    event.updated_at = now

    await record_audit(
        db,
        actor=user,
        action="compliance.event.status",
        target_type="compliance_event",
        target_id=event_id,
        detail={"status": data.status},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(event)
    counts = await _note_counts(db, [event.id])
    return _event_to_response(event, counts.get(event.id, 0))
