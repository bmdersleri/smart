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
    AGGREGATIONS,
    EVENT_STATUSES,
    LIMIT_TYPES,
    REPORT_FREQUENCIES,
    SOURCE_TYPES,
    ComplianceDischargePoint,
    ComplianceEvent,
    ComplianceEventNote,
    ComplianceLimit,
    ComplianceParameter,
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


class PermitUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    facility_name: str = ""
    authority: str = ""
    permit_number: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    report_frequency: str = "monthly"
    report_cron: str | None = None
    is_active: bool = True


class PointCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    lab_sample_point_id: int | None = None


class PointResponse(BaseModel):
    id: int
    permit_id: int
    code: str
    name: str
    description: str
    lab_sample_point_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ParameterCreate(BaseModel):
    discharge_point_id: int
    parameter_name: str = Field(min_length=1, max_length=255)
    unit: str = ""
    source_type: str
    tag_id: int | None = None
    lab_parameter_id: int | None = None


class ParameterUpdate(BaseModel):
    discharge_point_id: int
    parameter_name: str = Field(min_length=1, max_length=255)
    unit: str = ""
    source_type: str
    tag_id: int | None = None
    lab_parameter_id: int | None = None


class ParameterResponse(BaseModel):
    id: int
    permit_id: int
    discharge_point_id: int
    parameter_name: str
    unit: str
    source_type: str
    tag_id: int | None
    lab_parameter_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LimitCreate(BaseModel):
    limit_type: str
    min_value: float | None = None
    max_value: float | None = None
    aggregation: str
    window: str | None = None
    sample_frequency: str | None = None
    severity: str = "warning"
    requires_explanation: bool = False


class LimitResponse(BaseModel):
    id: int
    parameter_id: int
    limit_type: str
    min_value: float | None
    max_value: float | None
    aggregation: str
    window: str | None
    sample_frequency: str | None
    severity: str
    requires_explanation: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ParameterWithLimitsResponse(ParameterResponse):
    limits: list[LimitResponse] = []


class PermitDetailResponse(PermitResponse):
    discharge_points: list[PointResponse] = []
    parameters: list[ParameterWithLimitsResponse] = []


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


def _validate_report_frequency(report_frequency: str, report_cron: str | None) -> None:
    if report_frequency not in REPORT_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"report_frequency must be one of {REPORT_FREQUENCIES}",
        )
    if report_frequency == "custom_cron" and not report_cron:
        raise HTTPException(
            status_code=422,
            detail="report_cron is required when report_frequency is custom_cron",
        )


def _validate_source_mapping(
    source_type: str, tag_id: int | None, lab_parameter_id: int | None
) -> None:
    if source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"source_type must be one of {SOURCE_TYPES}")
    if source_type == "scada" and tag_id is None:
        raise HTTPException(status_code=422, detail="scada source_type requires tag_id")
    if source_type == "lab" and lab_parameter_id is None:
        raise HTTPException(status_code=422, detail="lab source_type requires lab_parameter_id")
    if source_type == "hybrid" and (tag_id is None or lab_parameter_id is None):
        raise HTTPException(
            status_code=422,
            detail="hybrid source_type requires both tag_id and lab_parameter_id",
        )


def _validate_limit(limit_type: str, aggregation: str) -> None:
    if limit_type not in LIMIT_TYPES:
        raise HTTPException(status_code=422, detail=f"limit_type must be one of {LIMIT_TYPES}")
    if aggregation not in AGGREGATIONS:
        raise HTTPException(status_code=422, detail=f"aggregation must be one of {AGGREGATIONS}")


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
    _validate_report_frequency(data.report_frequency, data.report_cron)

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


@router.get("/permits/{permit_id}", response_model=PermitDetailResponse)
async def get_permit(
    permit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PermitDetailResponse:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    points = list(
        (
            await db.execute(
                select(ComplianceDischargePoint)
                .where(ComplianceDischargePoint.permit_id == permit_id)
                .order_by(ComplianceDischargePoint.id)
            )
        )
        .scalars()
        .all()
    )
    parameters = list(
        (
            await db.execute(
                select(ComplianceParameter)
                .where(ComplianceParameter.permit_id == permit_id)
                .order_by(ComplianceParameter.id)
            )
        )
        .scalars()
        .all()
    )
    param_ids = [p.id for p in parameters]
    limits_by_param: dict[int, list[ComplianceLimit]] = {pid: [] for pid in param_ids}
    if param_ids:
        limit_rows = list(
            (
                await db.execute(
                    select(ComplianceLimit)
                    .where(ComplianceLimit.parameter_id.in_(param_ids))
                    .order_by(ComplianceLimit.id)
                )
            )
            .scalars()
            .all()
        )
        for limit in limit_rows:
            limits_by_param[limit.parameter_id].append(limit)

    return PermitDetailResponse(
        **PermitResponse.model_validate(permit).model_dump(),
        discharge_points=[PointResponse.model_validate(p) for p in points],
        parameters=[
            ParameterWithLimitsResponse(
                **ParameterResponse.model_validate(param).model_dump(),
                limits=[LimitResponse.model_validate(limit) for limit in limits_by_param[param.id]],
            )
            for param in parameters
        ],
    )


@router.put("/permits/{permit_id}", response_model=PermitResponse)
async def update_permit(
    permit_id: int,
    data: PermitUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> CompliancePermit:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    _validate_report_frequency(data.report_frequency, data.report_cron)

    permit.name = data.name
    permit.facility_name = data.facility_name
    permit.authority = data.authority
    permit.permit_number = data.permit_number
    permit.valid_from = data.valid_from.replace(tzinfo=None) if data.valid_from else None
    permit.valid_to = data.valid_to.replace(tzinfo=None) if data.valid_to else None
    permit.report_frequency = data.report_frequency
    permit.report_cron = data.report_cron
    permit.is_active = data.is_active
    permit.updated_at = datetime.utcnow()

    await record_audit(
        db,
        actor=user,
        action="compliance.permit.update",
        target_type="compliance_permit",
        target_id=permit.id,
        detail={"name": permit.name, "report_frequency": permit.report_frequency},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(permit)
    return permit


@router.delete("/permits/{permit_id}")
async def delete_permit(
    permit_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    # Soft delete only — permits are legal records with attached events/packs.
    # We never physically remove the row; deactivate it instead.
    permit.is_active = False
    permit.updated_at = datetime.utcnow()

    await record_audit(
        db,
        actor=user,
        action="compliance.permit.delete",
        target_type="compliance_permit",
        target_id=permit.id,
        detail={"soft_delete": True},
        ip=_client_ip(request),
    )
    await db.commit()
    return {"id": permit_id, "is_active": False}


# --------------------------------------------------------------------------
# Discharge points
# --------------------------------------------------------------------------


@router.get("/permits/{permit_id}/points", response_model=list[PointResponse])
async def list_points(
    permit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ComplianceDischargePoint]:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")
    return list(
        (
            await db.execute(
                select(ComplianceDischargePoint)
                .where(ComplianceDischargePoint.permit_id == permit_id)
                .order_by(ComplianceDischargePoint.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("/permits/{permit_id}/points", response_model=PointResponse, status_code=201)
async def create_point(
    permit_id: int,
    data: PointCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceDischargePoint:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    point = ComplianceDischargePoint(
        permit_id=permit_id,
        code=data.code,
        name=data.name,
        description=data.description,
        lab_sample_point_id=data.lab_sample_point_id,
    )
    db.add(point)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="compliance.point.create",
        target_type="compliance_discharge_point",
        target_id=point.id,
        detail={"permit_id": permit_id, "code": point.code},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(point)
    return point


@router.put("/points/{point_id}", response_model=PointResponse)
async def update_point(
    point_id: int,
    data: PointCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceDischargePoint:
    point = await db.get(ComplianceDischargePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Deşarj noktası bulunamadı")

    point.code = data.code
    point.name = data.name
    point.description = data.description
    point.lab_sample_point_id = data.lab_sample_point_id
    point.updated_at = datetime.utcnow()

    await record_audit(
        db,
        actor=user,
        action="compliance.point.update",
        target_type="compliance_discharge_point",
        target_id=point.id,
        detail={"code": point.code},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(point)
    return point


@router.delete("/points/{point_id}")
async def delete_point(
    point_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    point = await db.get(ComplianceDischargePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Deşarj noktası bulunamadı")
    await db.delete(point)
    await record_audit(
        db,
        actor=user,
        action="compliance.point.delete",
        target_type="compliance_discharge_point",
        target_id=point_id,
        detail={"permit_id": point.permit_id},
        ip=_client_ip(request),
    )
    await db.commit()
    return {"id": point_id, "deleted": True}


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


@router.get("/permits/{permit_id}/parameters", response_model=list[ParameterResponse])
async def list_parameters(
    permit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ComplianceParameter]:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")
    return list(
        (
            await db.execute(
                select(ComplianceParameter)
                .where(ComplianceParameter.permit_id == permit_id)
                .order_by(ComplianceParameter.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("/permits/{permit_id}/parameters", response_model=ParameterResponse, status_code=201)
async def create_parameter(
    permit_id: int,
    data: ParameterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceParameter:
    permit = await db.get(CompliancePermit, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit bulunamadı")

    _validate_source_mapping(data.source_type, data.tag_id, data.lab_parameter_id)

    point = await db.get(ComplianceDischargePoint, data.discharge_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Deşarj noktası bulunamadı")
    if point.permit_id != permit_id:
        raise HTTPException(
            status_code=400,
            detail="discharge_point_id must belong to the given permit",
        )

    parameter = ComplianceParameter(
        permit_id=permit_id,
        discharge_point_id=data.discharge_point_id,
        parameter_name=data.parameter_name,
        unit=data.unit,
        source_type=data.source_type,
        tag_id=data.tag_id,
        lab_parameter_id=data.lab_parameter_id,
    )
    db.add(parameter)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="compliance.parameter.create",
        target_type="compliance_parameter",
        target_id=parameter.id,
        detail={"permit_id": permit_id, "parameter_name": parameter.parameter_name},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(parameter)
    return parameter


@router.put("/parameters/{parameter_id}", response_model=ParameterResponse)
async def update_parameter(
    parameter_id: int,
    data: ParameterUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceParameter:
    parameter = await db.get(ComplianceParameter, parameter_id)
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parametre bulunamadı")

    _validate_source_mapping(data.source_type, data.tag_id, data.lab_parameter_id)

    point = await db.get(ComplianceDischargePoint, data.discharge_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Deşarj noktası bulunamadı")
    if point.permit_id != parameter.permit_id:
        raise HTTPException(
            status_code=400,
            detail="discharge_point_id must belong to the parameter's permit",
        )

    parameter.discharge_point_id = data.discharge_point_id
    parameter.parameter_name = data.parameter_name
    parameter.unit = data.unit
    parameter.source_type = data.source_type
    parameter.tag_id = data.tag_id
    parameter.lab_parameter_id = data.lab_parameter_id
    parameter.updated_at = datetime.utcnow()

    await record_audit(
        db,
        actor=user,
        action="compliance.parameter.update",
        target_type="compliance_parameter",
        target_id=parameter.id,
        detail={"parameter_name": parameter.parameter_name},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(parameter)
    return parameter


@router.delete("/parameters/{parameter_id}")
async def delete_parameter(
    parameter_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    parameter = await db.get(ComplianceParameter, parameter_id)
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parametre bulunamadı")
    await db.delete(parameter)
    await record_audit(
        db,
        actor=user,
        action="compliance.parameter.delete",
        target_type="compliance_parameter",
        target_id=parameter_id,
        detail={"permit_id": parameter.permit_id},
        ip=_client_ip(request),
    )
    await db.commit()
    return {"id": parameter_id, "deleted": True}


# --------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------


@router.get("/parameters/{parameter_id}/limits", response_model=list[LimitResponse])
async def list_limits(
    parameter_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ComplianceLimit]:
    parameter = await db.get(ComplianceParameter, parameter_id)
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parametre bulunamadı")
    return list(
        (
            await db.execute(
                select(ComplianceLimit)
                .where(ComplianceLimit.parameter_id == parameter_id)
                .order_by(ComplianceLimit.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("/parameters/{parameter_id}/limits", response_model=LimitResponse, status_code=201)
async def create_limit(
    parameter_id: int,
    data: LimitCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceLimit:
    parameter = await db.get(ComplianceParameter, parameter_id)
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parametre bulunamadı")

    _validate_limit(data.limit_type, data.aggregation)

    limit = ComplianceLimit(
        parameter_id=parameter_id,
        limit_type=data.limit_type,
        min_value=data.min_value,
        max_value=data.max_value,
        aggregation=data.aggregation,
        window=data.window,
        sample_frequency=data.sample_frequency,
        severity=data.severity,
        requires_explanation=data.requires_explanation,
    )
    db.add(limit)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="compliance.limit.create",
        target_type="compliance_limit",
        target_id=limit.id,
        detail={"parameter_id": parameter_id, "limit_type": limit.limit_type},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(limit)
    return limit


@router.put("/limits/{limit_id}", response_model=LimitResponse)
async def update_limit(
    limit_id: int,
    data: LimitCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> ComplianceLimit:
    limit = await db.get(ComplianceLimit, limit_id)
    if limit is None:
        raise HTTPException(status_code=404, detail="Limit bulunamadı")

    _validate_limit(data.limit_type, data.aggregation)

    limit.limit_type = data.limit_type
    limit.min_value = data.min_value
    limit.max_value = data.max_value
    limit.aggregation = data.aggregation
    limit.window = data.window
    limit.sample_frequency = data.sample_frequency
    limit.severity = data.severity
    limit.requires_explanation = data.requires_explanation
    limit.updated_at = datetime.utcnow()

    await record_audit(
        db,
        actor=user,
        action="compliance.limit.update",
        target_type="compliance_limit",
        target_id=limit.id,
        detail={"limit_type": limit.limit_type},
        ip=_client_ip(request),
    )
    await db.commit()
    await db.refresh(limit)
    return limit


@router.delete("/limits/{limit_id}")
async def delete_limit(
    limit_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    limit = await db.get(ComplianceLimit, limit_id)
    if limit is None:
        raise HTTPException(status_code=404, detail="Limit bulunamadı")
    await db.delete(limit)
    await record_audit(
        db,
        actor=user,
        action="compliance.limit.delete",
        target_type="compliance_limit",
        target_id=limit_id,
        detail={"parameter_id": limit.parameter_id},
        ip=_client_ip(request),
    )
    await db.commit()
    return {"id": limit_id, "deleted": True}


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
