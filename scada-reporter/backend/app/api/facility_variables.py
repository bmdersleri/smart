"""Tesis değişkenleri REST API: CRUD + validate + preview + dependencies."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_perm
from app.api.license_guard import require_writable
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import (
    PERM_FACILITY_VARIABLE_CREATE,
    PERM_FACILITY_VARIABLE_DELETE,
    PERM_FACILITY_VARIABLE_EDIT,
)
from app.models.facility_variable import FacilityVariable
from app.models.user import User
from app.services.facility_variables.expression import ExpressionError, validate_expression
from app.services.facility_variables.preview import PreviewBoundsError, preview_variable
from app.services.facility_variables.service import (
    VariableError,
    create_variable,
    deactivate_variable,
    update_variable,
)

router = APIRouter(prefix="/facility-variables", tags=["facility-variables"])


# --------------------------------------------------------------------------- schemas
class VariableCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    kind: str
    unit: str = ""
    value_type: str = "number"
    expression: dict
    null_policy: str = "skip"
    quality_policy: str = "good_only"
    default_time_grain: str | None = "day"


class VariableUpdate(BaseModel):
    name: str
    description: str = ""
    unit: str = ""
    expression: dict
    null_policy: str = "skip"
    quality_policy: str = "good_only"
    default_time_grain: str | None = "day"


class VariableResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    kind: str
    value_type: str
    unit: str
    expression: dict
    null_policy: str
    quality_policy: str
    default_time_grain: str | None
    is_active: bool
    version: int
    dependency_count: int

    @classmethod
    def of(cls, v: FacilityVariable) -> VariableResponse:
        return cls(
            id=v.id,
            code=v.code,
            name=v.name,
            description=v.description,
            kind=v.kind,
            value_type=v.value_type,
            unit=v.unit,
            expression=json.loads(v.expression_json),
            null_policy=v.null_policy,
            quality_policy=v.quality_policy,
            default_time_grain=v.default_time_grain,
            is_active=v.is_active,
            version=v.version,
            dependency_count=len(v.dependencies),
        )


class ValidateRequest(BaseModel):
    expression: dict
    kind: str


class WindowSpec(BaseModel):
    type: str  # month|last_24h|last_7d|last_30d|custom
    year: int | None = None
    month: int | None = None
    start: datetime | None = None
    end: datetime | None = None


class PreviewRequest(BaseModel):
    window: WindowSpec
    grain: str | None = None
    tz_offset_hours: int | None = None


# --------------------------------------------------------------------------- helpers
def _resolve_window(w: WindowSpec) -> tuple[datetime, datetime]:
    if w.type == "month":
        if w.year is None or w.month is None:
            raise HTTPException(422, "month penceresi year+month ister")
        start = datetime(w.year, w.month, 1)
        end = datetime(w.year + 1, 1, 1) if w.month == 12 else datetime(w.year, w.month + 1, 1)
        return start, end
    if w.type == "custom":
        if w.start is None or w.end is None:
            raise HTTPException(422, "custom penceresi start+end ister")
        return w.start.replace(tzinfo=None), w.end.replace(tzinfo=None)
    raise HTTPException(422, f"Desteklenmeyen window tipi: {w.type}")


# --------------------------------------------------------------------------- routes
@router.get("", response_model=list[VariableResponse])
async def list_variables(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await db.execute(select(FacilityVariable).order_by(FacilityVariable.code))
    return [VariableResponse.of(v) for v in rows.scalars().all()]


@router.post("", response_model=VariableResponse, status_code=201)
async def create(
    body: VariableCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm(PERM_FACILITY_VARIABLE_CREATE)),
    _w: None = Depends(require_writable),
):
    try:
        var = await create_variable(
            db,
            code=body.code,
            name=body.name,
            description=body.description,
            kind=body.kind,
            unit=body.unit,
            expression=body.expression,
            null_policy=body.null_policy,
            quality_policy=body.quality_policy,
            default_time_grain=body.default_time_grain,
            value_type=body.value_type,
            created_by=user.id,
        )
    except VariableError as e:
        raise HTTPException(422, str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(409, "Bu code zaten var") from e
    return VariableResponse.of(var)


@router.get("/{var_id}", response_model=VariableResponse)
async def detail(
    var_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    return VariableResponse.of(var)


@router.put("/{var_id}", response_model=VariableResponse)
async def update(
    var_id: int,
    body: VariableUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm(PERM_FACILITY_VARIABLE_EDIT)),
    _w: None = Depends(require_writable),
):
    try:
        var = await update_variable(
            db,
            var_id,
            name=body.name,
            description=body.description,
            unit=body.unit,
            expression=body.expression,
            null_policy=body.null_policy,
            quality_policy=body.quality_policy,
            default_time_grain=body.default_time_grain,
            updated_by=user.id,
        )
    except VariableError as e:
        raise HTTPException(422, str(e)) from e
    return VariableResponse.of(var)


@router.delete("/{var_id}", status_code=204)
async def soft_delete(
    var_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm(PERM_FACILITY_VARIABLE_DELETE)),
    _w: None = Depends(require_writable),
):
    try:
        await deactivate_variable(db, var_id, force=force)
    except VariableError as e:
        msg = str(e)
        if "bulunamadı" in msg:
            raise HTTPException(404, msg) from e
        raise HTTPException(409, msg) from e


@router.post("/validate")
async def validate(body: ValidateRequest, _: User = Depends(get_current_user)):
    try:
        validate_expression(body.expression, body.kind)
    except ExpressionError as e:
        raise HTTPException(422, str(e)) from e
    return {"valid": True}


@router.post("/{var_id}/preview")
async def preview(
    var_id: int,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    start, end = _resolve_window(body.window)
    grain = body.grain or var.default_time_grain or "day"
    tz = (
        body.tz_offset_hours
        if body.tz_offset_hours is not None
        else settings.REPORT_TZ_OFFSET_HOURS
    )
    try:
        return await preview_variable(
            db, var, start=start, end=end, grain=grain, tz_offset_hours=tz
        )
    except PreviewBoundsError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{var_id}/dependencies")
async def dependencies(
    var_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    return [
        {
            "depends_on_type": d.depends_on_type,
            "depends_on_tag_id": d.depends_on_tag_id,
            "depends_on_variable_id": d.depends_on_variable_id,
        }
        for d in var.dependencies
    ]
