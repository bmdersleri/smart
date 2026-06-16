import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.tag import Tag, TagReading
from app.models.user import User
from app.models.watchlist import Watchlist

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    now = datetime.now(UTC)
    tag_count = await db.scalar(select(func.count(Tag.id)).where(Tag.is_active, Tag.long_term))
    last_reading = await db.scalar(select(func.max(TagReading.timestamp)))
    reading_count_24h = await db.scalar(
        select(func.count(TagReading.timestamp)).where(
            TagReading.timestamp >= now - timedelta(hours=24)
        )
    )
    since_1h = now - timedelta(hours=1)
    reading_count_1h = await db.scalar(
        select(func.count(TagReading.timestamp)).where(TagReading.timestamp >= since_1h)
    )
    good_count_1h = await db.scalar(
        select(func.count(TagReading.timestamp)).where(
            TagReading.timestamp >= since_1h,
            TagReading.quality == 192,
        )
    )
    quality_rate = (
        round((good_count_1h or 0) / reading_count_1h * 100) if reading_count_1h else None
    )
    return {
        "active_tags": tag_count,
        "last_reading": last_reading,
        "readings_24h": reading_count_24h,
        "readings_1h": reading_count_1h,
        "quality_rate": quality_rate,
    }


# ---------------------------------------------------------------------------
# Devices list (for filter dropdown)
# ---------------------------------------------------------------------------


@router.get("/devices")
async def devices(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(distinct(Tag.device))
        .where(Tag.is_active, Tag.long_term, Tag.device != "")
        .order_by(Tag.device)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


def _latest_reading_subq(tag_ids: list[int]):
    return (
        select(TagReading.tag_id, func.max(TagReading.timestamp).label("max_ts"))
        .where(TagReading.tag_id.in_(tag_ids))
        .group_by(TagReading.tag_id)
        .subquery()
    )


async def _fetch_tags_with_readings(db: AsyncSession, tag_ids: list[int]) -> list[dict]:
    if not tag_ids:
        return []
    subq = _latest_reading_subq(tag_ids)
    result = await db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.device,
            Tag.unit,
            Tag.sample_interval,
            TagReading.value,
            TagReading.timestamp,
            TagReading.quality,
        )
        .outerjoin(subq, Tag.id == subq.c.tag_id)
        .outerjoin(
            TagReading,
            (TagReading.tag_id == subq.c.tag_id) & (TagReading.timestamp == subq.c.max_ts),
        )
        .where(Tag.id.in_(tag_ids))
        .order_by(Tag.device, Tag.name)
    )
    rows = result.all()
    return [
        {
            "tag_id": r[0],
            "name": r[1],
            "device": r[2],
            "unit": r[3],
            "value": r[5],
            "timestamp": r[6],
            "quality_ok": r[7] == 192 if r[7] is not None else False,
        }
        for r in rows
    ]


@router.get("/watchlist")
async def get_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag_ids_result = await db.execute(
        select(Watchlist.tag_id).where(Watchlist.user_id == current_user.id)
    )
    tag_ids = tag_ids_result.scalars().all()
    return await _fetch_tags_with_readings(db, list(tag_ids))


@router.post("/watchlist/{tag_id}", status_code=status.HTTP_201_CREATED)
async def add_watchlist(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadı")
    existing = await db.scalar(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.tag_id == tag_id)
    )
    if existing:
        return {"status": "already_exists"}
    db.add(Watchlist(user_id=current_user.id, tag_id=tag_id))
    await db.commit()
    return {"status": "added"}


@router.delete("/watchlist/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.tag_id == tag_id)
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


# ---------------------------------------------------------------------------
# Filtered + paginated tags
# ---------------------------------------------------------------------------


@router.get("/tags")
async def dashboard_tags(
    device: str | None = Query(None),
    search: str | None = Query(None),
    quality: Literal["good", "bad", "stale"] | None = Query(None),
    daily: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # 1. Build base tag query (active archive tags only)
    base = select(Tag).where(Tag.is_active, Tag.long_term)
    if device:
        base = base.where(Tag.device == device)
    if search:
        base = base.where(Tag.name.ilike(f"%{search}%"))
    if daily is not None:
        base = base.where(Tag.daily_tracking == daily)

    # 2. Count total (before quality filter which is post-fetch)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0

    # 3. Paginate tag rows
    tags_result = await db.execute(
        base.order_by(Tag.device, Tag.name).offset((page - 1) * page_size).limit(page_size)
    )
    tags = tags_result.scalars().all()

    if not tags:
        return {
            "items": [],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, math.ceil(total / page_size)),
        }

    tag_ids = [t.id for t in tags]

    # 4. Fetch latest readings for this page's tags only
    subq = _latest_reading_subq(tag_ids)
    readings_result = await db.execute(
        select(
            TagReading.tag_id,
            TagReading.value,
            TagReading.timestamp,
            TagReading.quality,
        )
        .join(subq, (TagReading.tag_id == subq.c.tag_id) & (TagReading.timestamp == subq.c.max_ts))
        .where(TagReading.tag_id.in_(tag_ids))
    )
    readings = {r[0]: r for r in readings_result.all()}

    now = datetime.now(UTC)

    # 5. Build items + apply quality filter in Python
    items = []
    for t in tags:
        r = readings.get(t.id)
        value = r[1] if r else None
        ts = r[2] if r else None
        q = r[3] if r else None
        quality_ok = q == 192 if q is not None else False

        if quality == "good" and not quality_ok:
            continue
        if quality == "bad" and quality_ok:
            continue
        if quality == "stale":
            stale_threshold = timedelta(seconds=3 * (t.sample_interval or 5))
            is_stale = ts is None or (now - ts.replace(tzinfo=UTC) > stale_threshold)
            if not is_stale:
                continue

        items.append(
            {
                "tag_id": t.id,
                "name": t.name,
                "device": t.device,
                "unit": t.unit,
                "value": value,
                "timestamp": ts,
                "quality_ok": quality_ok,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


# ---------------------------------------------------------------------------
# Trend (unchanged)
# ---------------------------------------------------------------------------


def downsample(data: list[dict], max_points: int | None) -> list[dict]:
    """Seriyi eşit aralıklı stride ile en fazla max_points noktaya indir.

    İlk ve son nokta korunur. max_points None veya seri zaten kısa ise olduğu
    gibi döner. Çok-noktalı 24sa trend'lerini grafik için hafifletir.
    """
    if max_points is None or len(data) <= max_points:
        return data
    if max_points <= 2:
        return [data[0], data[-1]]
    step = (len(data) - 1) / (max_points - 1)
    out = [data[round(i * step)] for i in range(max_points)]
    out[-1] = data[-1]
    return out


@router.get("/trend")
async def trend(
    tag_ids: list[int] = Query(...),
    hours: int = 24,
    max_points: int | None = Query(None, ge=2),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    since = datetime.now(UTC) - timedelta(hours=hours)
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

    out = list(series.values())
    for s in out:
        s["data"] = downsample(s["data"], max_points)
    return out
