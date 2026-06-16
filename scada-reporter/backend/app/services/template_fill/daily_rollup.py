"""Günlük tag toplama arayüzü.

Tek giriş noktası: daily_values(). PostgreSQL/Timescale'de tag_readings_1d
sürekli toplama view'ından okur; SQLite/dev'de ham tag_readings'i Python'da
gün bazında gruplar. delta = günün son okuması - ilk okuması.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import TagReading

AGGS = {"sum", "avg", "min", "max", "last", "delta"}


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _reduce(values: list[float], agg: str) -> float | None:
    """values: günün okumaları, zaman sırasına göre. agg uygula."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if agg == "sum":
        return sum(vals)
    if agg == "avg":
        return sum(vals) / len(vals)
    if agg == "min":
        return min(vals)
    if agg == "max":
        return max(vals)
    if agg == "last":
        return vals[-1]
    if agg == "delta":
        return vals[-1] - vals[0] if len(vals) >= 2 else None
    raise ValueError(f"Bilinmeyen agg: {agg}")


async def _daily_sqlite(
    db: AsyncSession, tag_id: int, year: int, month: int, agg: str, tz_offset_hours: int
) -> dict[int, float]:
    start, end = _month_bounds(year, month)
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    result = await db.execute(
        select(TagReading.timestamp, TagReading.value)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= q_start,
            TagReading.timestamp < q_end,
        )
        .order_by(TagReading.timestamp.asc())
    )
    buckets: dict[int, list[float]] = defaultdict(list)
    for ts, value in result.all():
        local = ts + timedelta(hours=tz_offset_hours)
        if local.year == year and local.month == month:
            buckets[local.day].append(value)
    out: dict[int, float] = {}
    for day, vals in buckets.items():
        reduced = _reduce(vals, agg)
        if reduced is not None:
            out[day] = reduced
    return out


_CAGG_COL = {"sum": "sum", "avg": "avg", "min": "min", "max": "max", "last": "last_v"}


async def _daily_timescale(
    db: AsyncSession, tag_id: int, year: int, month: int, agg: str, tz_offset_hours: int
) -> dict[int, float]:
    start, end = _month_bounds(year, month)
    shift = f"INTERVAL '{tz_offset_hours} hours'"
    if agg == "delta":
        rows = await db.execute(
            text(
                "SELECT EXTRACT(DAY FROM (bucket + " + shift + "))::int AS d, "
                "(last_v - first_v) AS val, n "
                "FROM tag_readings_1d "
                "WHERE tag_id = :tid AND (bucket + " + shift + ") >= :s "
                "AND (bucket + " + shift + ") < :e"
            ),
            {"tid": tag_id, "s": start, "e": end},
        )
        return {int(d): float(v) for d, v, n in rows.all() if v is not None and n >= 2}
    col = _CAGG_COL[agg]
    rows = await db.execute(
        text(
            "SELECT EXTRACT(DAY FROM (bucket + " + shift + "))::int AS d, "
            f"{col} AS val FROM tag_readings_1d "
            "WHERE tag_id = :tid AND (bucket + " + shift + ") >= :s "
            "AND (bucket + " + shift + ") < :e"
        ),
        {"tid": tag_id, "s": start, "e": end},
    )
    return {int(d): float(v) for d, v in rows.all() if v is not None}


async def daily_values(
    db: AsyncSession,
    tag_id: int,
    year: int,
    month: int,
    agg: str,
    tz_offset_hours: int = 0,
) -> dict[int, float]:
    """{gün_no: değer} döndür. Verisi olmayan gün anahtarsız (sıfır uydurma yok)."""
    if agg not in AGGS:
        raise ValueError(f"Bilinmeyen agg: {agg}")
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "postgresql":
        return await _daily_timescale(db, tag_id, year, month, agg, tz_offset_hours)
    return await _daily_sqlite(db, tag_id, year, month, agg, tz_offset_hours)
