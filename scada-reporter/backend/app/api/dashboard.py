from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.tag import Tag, TagReading

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Toplam tag sayısı, son okuma zamanı gibi genel bilgiler."""
    tag_count = await db.scalar(select(func.count(Tag.id)).where(Tag.is_active == True))
    last_reading = await db.scalar(select(func.max(TagReading.timestamp)))
    reading_count_24h = await db.scalar(
        select(func.count(TagReading.id)).where(
            TagReading.timestamp >= datetime.utcnow() - timedelta(hours=24)
        )
    )
    return {
        "active_tags": tag_count,
        "last_reading": last_reading,
        "readings_24h": reading_count_24h,
    }


@router.get("/trend")
async def trend(
    tag_ids: list[int] = Query(...),
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Birden fazla tag için zaman serisi verisi."""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(Tag.id, Tag.name, Tag.unit, TagReading.timestamp, TagReading.value)
        .join(TagReading, Tag.id == TagReading.tag_id)
        .where(Tag.id.in_(tag_ids), TagReading.timestamp >= since)
        .order_by(TagReading.timestamp.asc())
    )
    rows = result.all()

    series: dict[int, dict] = {}
    for tag_id, name, unit, ts, value in rows:
        if tag_id not in series:
            series[tag_id] = {"tag_id": tag_id, "name": name, "unit": unit, "data": []}
        series[tag_id]["data"].append({"t": ts.isoformat(), "v": value})

    return list(series.values())


@router.get("/current-values")
async def current_values(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Her aktif tag için en son değer."""
    subq = (
        select(TagReading.tag_id, func.max(TagReading.timestamp).label("max_ts"))
        .group_by(TagReading.tag_id)
        .subquery()
    )
    result = await db.execute(
        select(Tag.id, Tag.name, Tag.unit, Tag.device, TagReading.value, TagReading.timestamp, TagReading.quality)
        .join(subq, Tag.id == subq.c.tag_id)
        .join(TagReading, (TagReading.tag_id == subq.c.tag_id) & (TagReading.timestamp == subq.c.max_ts))
        .where(Tag.is_active == True)
        .order_by(Tag.device, Tag.name)
    )
    rows = result.all()
    return [
        {
            "tag_id": r[0], "name": r[1], "unit": r[2], "device": r[3],
            "value": r[4], "timestamp": r[5], "quality_ok": r[6] == 192,
        }
        for r in rows
    ]
