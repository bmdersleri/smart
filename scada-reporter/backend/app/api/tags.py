from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from app.core.database import get_db
from app.api.auth import get_current_user, require_role
from app.models.tag import Tag, TagReading
from app.collector.opc_client import collector

router = APIRouter(prefix="/tags", tags=["tags"])


class TagCreate(BaseModel):
    node_id: str
    name: str
    description: str = ""
    unit: str = ""
    channel: str = ""
    device: str = ""


class TagResponse(BaseModel):
    id: int
    node_id: str
    name: str
    description: str
    unit: str
    channel: str
    device: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("/browse")
async def browse_tags(_=Depends(get_current_user)):
    """KEPServerEX tag ağacını tarar."""
    try:
        tags = await collector.browse_tags()
        return {"tags": tags, "count": len(tags)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OPC UA baglantisi hatasi: {e}")


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


@router.get("/{tag_id}/readings")
async def get_readings(
    tag_id: int,
    start: datetime = None,
    end: datetime = None,
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
