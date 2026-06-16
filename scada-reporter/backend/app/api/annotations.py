"""Trend annotation (paylaşımlı not) API — DB destekli, tüm kullanıcılar görür."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.core.database import get_db
from app.models.annotation import Annotation
from app.models.user import User

router = APIRouter(prefix="/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    tag_id: int | None = None
    ts: datetime
    text: str


class AnnotationResponse(BaseModel):
    id: int
    tag_id: int | None
    username: str
    ts: datetime
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[AnnotationResponse])
async def list_annotations(
    tag_ids: list[int] | None = Query(None),
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Annotation)
    if tag_ids:
        # seçili tag'lerin notları + grafik-seviyesi (tag_id IS NULL) notlar
        stmt = stmt.where(Annotation.tag_id.in_(tag_ids) | Annotation.tag_id.is_(None))
    if start:
        stmt = stmt.where(Annotation.ts >= start)
    if end:
        stmt = stmt.where(Annotation.ts <= end)
    stmt = stmt.order_by(Annotation.ts.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=AnnotationResponse, status_code=201)
async def create_annotation(
    data: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    ann = Annotation(
        tag_id=data.tag_id,
        user_id=user.id,
        username=user.username,
        ts=data.ts.replace(tzinfo=None),
        text=data.text,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="Not bulunamadı")
    if ann.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Sadece sahibi veya admin silebilir")
    await db.delete(ann)
    await db.commit()
