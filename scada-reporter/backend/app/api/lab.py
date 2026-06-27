from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
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
