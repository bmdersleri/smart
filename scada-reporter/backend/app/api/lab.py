from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.database import get_db
from app.models.lab import LabParameter, LabSamplePoint
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
