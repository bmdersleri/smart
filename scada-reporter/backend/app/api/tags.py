from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.core.database import get_db
from app.models.tag import Tag, TagReading

router = APIRouter(prefix="/tags", tags=["tags"])


class TagCreate(BaseModel):
    node_id: str
    name: str
    description: str = ""
    unit: str = ""
    channel: str = ""
    device: str = ""


class TagUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    device: str | None = None
    channel: str | None = None
    description: str | None = None
    min_alarm: float | None = None
    max_alarm: float | None = None


class TagResponse(BaseModel):
    id: int
    node_id: str
    name: str
    description: str
    unit: str
    channel: str
    device: str
    is_active: bool
    min_alarm: float | None
    max_alarm: float | None

    model_config = {"from_attributes": True}


@router.get("/browse")
async def browse_tags(_=Depends(get_current_user)):
    """snap7 ile otomatik tag kesfi desteklenmez — bos liste doner."""
    return {"tags": [], "count": 0}


@router.get("/", response_model=list[TagResponse])
async def list_tags(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Tag).order_by(Tag.device, Tag.name))
    return result.scalars().all()


@router.post("/", response_model=TagResponse, status_code=201)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    tag = Tag(**data.model_dump())
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadi")
    await db.delete(tag)
    await db.commit()


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.get("/{tag_id}/readings")
async def get_readings(
    tag_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    conditions = [TagReading.tag_id == tag_id]
    if start:
        conditions.append(TagReading.timestamp >= start)
    if end:
        conditions.append(TagReading.timestamp <= end)

    result = await db.execute(
        select(TagReading)
        .where(and_(*conditions))
        .order_by(TagReading.timestamp.desc())
        .limit(limit)
    )
    readings = result.scalars().all()
    return [{"timestamp": r.timestamp, "value": r.value, "quality": r.quality} for r in readings]
