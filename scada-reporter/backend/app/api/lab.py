from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.audit import record_audit
from app.core.database import get_db
from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint
from app.models.tag import TagReading
from app.models.user import User

router = APIRouter(prefix="/lab", tags=["lab"])


# ---- Pydantic schemas ----
class LabParameterCreate(BaseModel):
    code: str
    name: str
    unit: str = ""
    category: str = ""
    min_limit: float | None = None
    max_limit: float | None = None
    mirror_to_tag_id: int | None = None


class LabParameterUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    category: str | None = None
    min_limit: float | None = None
    max_limit: float | None = None
    is_active: bool | None = None
    approved: bool | None = None
    mirror_to_tag_id: int | None = None


class LabParameterOut(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    category: str
    min_limit: float | None
    max_limit: float | None
    is_active: bool
    approved: bool
    mirror_to_tag_id: int | None
    model_config = {"from_attributes": True}


class LabSamplePointCreate(BaseModel):
    code: str
    name: str
    description: str = ""


class LabSamplePointUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    approved: bool | None = None


class LabSamplePointOut(BaseModel):
    id: int
    code: str
    name: str
    description: str
    is_active: bool
    approved: bool
    model_config = {"from_attributes": True}


# ---- Parameters ----
@router.get("/parameters", response_model=list[LabParameterOut])
async def list_parameters(
    approved: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(LabParameter).order_by(LabParameter.code)
    if approved is not None:
        query = query.where(LabParameter.approved == approved)
    if active is not None:
        query = query.where(LabParameter.is_active == active)
    return (await db.execute(query)).scalars().all()


@router.post("/parameters", response_model=LabParameterOut, status_code=201)
async def create_parameter(
    data: LabParameterCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    exists = await db.execute(select(LabParameter).where(LabParameter.code == data.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Parametre kodu zaten mevcut")
    param = LabParameter(**data.model_dump(), approved=(user.role == "admin"))
    db.add(param)
    await db.commit()
    await db.refresh(param)
    return param


@router.patch("/parameters/{param_id}", response_model=LabParameterOut)
async def update_parameter(
    param_id: int,
    data: LabParameterUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    param = (
        await db.execute(select(LabParameter).where(LabParameter.id == param_id))
    ).scalar_one_or_none()
    if not param:
        raise HTTPException(status_code=404, detail="Parametre bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(param, field, value)
    await db.commit()
    await db.refresh(param)
    return param


@router.delete("/parameters/{param_id}", status_code=204)
async def delete_parameter(
    param_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await db.execute(sa_delete(LabParameter).where(LabParameter.id == param_id))
    await db.commit()


# ---- Sample points ----
@router.get("/sample-points", response_model=list[LabSamplePointOut])
async def list_sample_points(
    approved: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(LabSamplePoint).order_by(LabSamplePoint.code)
    if approved is not None:
        query = query.where(LabSamplePoint.approved == approved)
    if active is not None:
        query = query.where(LabSamplePoint.is_active == active)
    return (await db.execute(query)).scalars().all()


@router.post("/sample-points", response_model=LabSamplePointOut, status_code=201)
async def create_sample_point(
    data: LabSamplePointCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    exists = await db.execute(select(LabSamplePoint).where(LabSamplePoint.code == data.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Nokta kodu zaten mevcut")
    point = LabSamplePoint(**data.model_dump(), approved=(user.role == "admin"))
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


@router.patch("/sample-points/{point_id}", response_model=LabSamplePointOut)
async def update_sample_point(
    point_id: int,
    data: LabSamplePointUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    point = (
        await db.execute(select(LabSamplePoint).where(LabSamplePoint.id == point_id))
    ).scalar_one_or_none()
    if not point:
        raise HTTPException(status_code=404, detail="Nokta bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(point, field, value)
    await db.commit()
    await db.refresh(point)
    return point


@router.delete("/sample-points/{point_id}", status_code=204)
async def delete_sample_point(
    point_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await db.execute(sa_delete(LabSamplePoint).where(LabSamplePoint.id == point_id))
    await db.commit()


# ---- Sample entry ----
class MeasurementIn(BaseModel):
    parameter_id: int
    value: float | None = None
    text_value: str | None = None


class SampleCreate(BaseModel):
    sample_point_id: int
    sampled_at: datetime
    method: str = ""
    batch_no: str = ""
    note: str = ""
    measurements: list[MeasurementIn] = []


class MeasurementOut(BaseModel):
    id: int
    parameter_id: int
    value: float | None
    text_value: str | None
    flag: str | None
    model_config = {"from_attributes": True}


class SampleOut(BaseModel):
    id: int
    sample_point_id: int
    sampled_at: datetime
    entered_by: int
    method: str
    batch_no: str
    note: str
    measurements: list[MeasurementOut]
    model_config = {"from_attributes": True}


def compute_flag(
    value: float | None, min_limit: float | None, max_limit: float | None
) -> str | None:
    if value is None:
        return None
    if min_limit is not None and value < min_limit:
        return "over_limit"
    if max_limit is not None and value > max_limit:
        return "over_limit"
    return None


async def _build_sample(db: AsyncSession, data: SampleCreate, entered_by: int) -> LabSample:
    """Create a LabSample + its measurements (with flag + mirror) in the session.

    Does NOT commit — caller owns the transaction boundary.
    """
    sample = LabSample(
        sample_point_id=data.sample_point_id,
        sampled_at=data.sampled_at,
        entered_by=entered_by,
        method=data.method,
        batch_no=data.batch_no,
        note=data.note,
    )
    db.add(sample)
    await db.flush()  # sample.id

    # preload referenced parameters for limits + mirror target
    param_ids = [m.parameter_id for m in data.measurements]
    params = {}
    if param_ids:
        rows = await db.execute(select(LabParameter).where(LabParameter.id.in_(param_ids)))
        params = {p.id: p for p in rows.scalars().all()}

    for m in data.measurements:
        param = params.get(m.parameter_id)
        if param is None:
            raise HTTPException(status_code=400, detail=f"Parametre yok: {m.parameter_id}")
        flag = compute_flag(m.value, param.min_limit, param.max_limit)
        db.add(
            LabMeasurement(
                sample_id=sample.id,
                parameter_id=m.parameter_id,
                value=m.value,
                text_value=m.text_value,
                flag=flag,
            )
        )
        if param.mirror_to_tag_id is not None and m.value is not None:
            db.add(
                TagReading(
                    tag_id=param.mirror_to_tag_id,
                    value=m.value,
                    quality=192,
                    timestamp=data.sampled_at,
                )
            )
    return sample


@router.post("/samples", response_model=SampleOut, status_code=201)
async def create_sample(
    data: SampleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _build_sample(db, data, entered_by=user.id)
    await db.commit()
    await db.refresh(sample, attribute_names=["measurements"])
    return sample


class BatchCreate(BaseModel):
    rows: list[SampleCreate]


@router.post("/samples/batch", status_code=201)
async def create_samples_batch(
    data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    ids = []
    for row in data.rows:
        sample = await _build_sample(db, row, entered_by=user.id)
        await db.flush()
        ids.append(sample.id)
    await db.commit()
    return {"inserted": len(ids), "sample_ids": ids}


# ---- List / get / edit / delete with ownership + audit ----


def _assert_can_edit(user: User, sample: LabSample) -> None:
    if user.role != "admin" and sample.entered_by != user.id:
        raise HTTPException(status_code=403, detail="Yalnizca kendi kaydinizi duzenleyebilirsiniz")


@router.get("/samples", response_model=list[SampleOut])
async def list_samples(
    point_id: int | None = Query(default=None),
    parameter_id: int | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    entered_by: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    conditions = []
    if point_id is not None:
        conditions.append(LabSample.sample_point_id == point_id)
    if start is not None:
        conditions.append(LabSample.sampled_at >= start)
    if end is not None:
        conditions.append(LabSample.sampled_at <= end)
    if entered_by is not None:
        conditions.append(LabSample.entered_by == entered_by)
    query = select(LabSample).options(selectinload(LabSample.measurements))
    if parameter_id is not None:
        query = query.join(LabMeasurement).where(LabMeasurement.parameter_id == parameter_id)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(LabSample.sampled_at.desc()).limit(limit).offset(offset).distinct()
    samples = (await db.execute(query)).scalars().unique().all()
    return samples


async def _get_sample_or_404(db: AsyncSession, sample_id: int) -> LabSample:
    sample = (
        await db.execute(
            select(LabSample)
            .options(selectinload(LabSample.measurements))
            .where(LabSample.id == sample_id)
        )
    ).scalar_one_or_none()
    if not sample:
        raise HTTPException(status_code=404, detail="Numune bulunamadi")
    return sample


@router.get("/samples/{sample_id}", response_model=SampleOut)
async def get_sample(
    sample_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await _get_sample_or_404(db, sample_id)


@router.patch("/samples/{sample_id}", response_model=SampleOut)
async def update_sample(
    sample_id: int,
    data: SampleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _get_sample_or_404(db, sample_id)
    _assert_can_edit(user, sample)
    # Update scalar fields
    sample.sample_point_id = data.sample_point_id
    sample.sampled_at = data.sampled_at
    sample.method = data.method
    sample.batch_no = data.batch_no
    sample.note = data.note
    # Full replace of measurements (clears + rebuilds; mirror not re-applied on edit)
    for existing in list(sample.measurements):
        await db.delete(existing)
    await db.flush()
    param_ids = [m.parameter_id for m in data.measurements]
    params = {}
    if param_ids:
        rows = await db.execute(select(LabParameter).where(LabParameter.id.in_(param_ids)))
        params = {p.id: p for p in rows.scalars().all()}
    for m in data.measurements:
        param = params.get(m.parameter_id)
        if param is None:
            raise HTTPException(status_code=400, detail=f"Parametre yok: {m.parameter_id}")
        db.add(
            LabMeasurement(
                sample_id=sample.id,
                parameter_id=m.parameter_id,
                value=m.value,
                text_value=m.text_value,
                flag=compute_flag(m.value, param.min_limit, param.max_limit),
            )
        )
    await record_audit(
        db,
        actor=user,
        action="lab.sample.update",
        target_type="lab_sample",
        target_id=sample.id,
        detail={"sample_point_id": data.sample_point_id, "n_measurements": len(data.measurements)},
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(sample, attribute_names=["measurements"])
    return sample


@router.delete("/samples/{sample_id}", status_code=204)
async def delete_sample(
    sample_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _get_sample_or_404(db, sample_id)
    _assert_can_edit(user, sample)
    await record_audit(
        db,
        actor=user,
        action="lab.sample.delete",
        target_type="lab_sample",
        target_id=sample.id,
        detail={"sample_point_id": sample.sample_point_id},
        ip=request.client.host if request.client else None,
    )
    await db.delete(sample)
    await db.commit()
