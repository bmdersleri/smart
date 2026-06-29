"""Ham tag_readings'i bucket'lara böler. daily_rollup.reduce_values ortak primitifi
kullanılır — agg matematiği tek yerde. tz_offset her bucket sınırına uygulanır.

v1: dialect-bağımsız Python tarafı bucketing (doğruluk önceliği). PostgreSQL
sürekli-toplama (cagg) yönlendirmesi sonraki planın perf işidir; aynı sayıları
üretmeli (parity testleri kilitler).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import TagReading
from app.services.template_fill.daily_rollup import reduce_values

GRAINS = ("hour", "day", "week", "month")

_RELATIVE = {
    "hour": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "day": timedelta(days=1),
    "7d": timedelta(days=7),
    "week": timedelta(days=7),
    "30d": timedelta(days=30),
}


def resolve_window(window: str, *, ref_end: datetime) -> tuple[datetime, datetime]:
    """Göreli pencereyi [start, end) naif-UTC aralığına çevir."""
    delta = _RELATIVE.get(window)
    if delta is None:
        raise ValueError(f"Bilinmeyen window: {window!r}")
    return ref_end - delta, ref_end


def _bucket_key(local: datetime, grain: str) -> datetime:
    """Yerel zaman damgasını grain bucket başlangıcına indirger."""
    if grain == "hour":
        return local.replace(minute=0, second=0, microsecond=0)
    if grain == "day":
        return datetime(local.year, local.month, local.day)
    if grain == "week":
        monday = local - timedelta(days=local.weekday())
        return datetime(monday.year, monday.month, monday.day)
    if grain == "month":
        return datetime(local.year, local.month, 1)
    raise ValueError(f"Bilinmeyen grain: {grain!r}")


async def _fetch(db: AsyncSession, tag_id: int, start: datetime, end: datetime):
    """[start, end) penceresini, tz kaymasını karşılayacak şekilde okur."""
    result = await db.execute(
        select(TagReading.timestamp, TagReading.value)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= start,
            TagReading.timestamp < end,
        )
        .order_by(TagReading.timestamp.asc())
    )
    return result.all()


async def agg_window(
    db: AsyncSession,
    tag_id: int,
    start: datetime,
    end: datetime,
    agg: str,
    tz_offset_hours: int,
) -> float | None:
    """[start, end) penceresinde tek bir indirgenmiş değer."""
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    rows = await _fetch(db, tag_id, q_start, q_end)
    vals = [v for _, v in rows]
    return reduce_values(vals, agg)


async def bucket_series(
    db: AsyncSession,
    tag_id: int,
    start: datetime,
    end: datetime,
    grain: str,
    agg: str,
    tz_offset_hours: int,
) -> dict[datetime, float]:
    """{yerel_bucket_başlangıcı: değer}. Verisi olmayan bucket anahtarsız."""
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    rows = await _fetch(db, tag_id, q_start, q_end)
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for ts, value in rows:
        local = ts + timedelta(hours=tz_offset_hours)
        if start <= local < end:
            buckets[_bucket_key(local, grain)].append(value)
    out: dict[datetime, float] = {}
    for key, vals in buckets.items():
        reduced = reduce_values(vals, agg)
        if reduced is not None:
            out[key] = reduced
    return out
