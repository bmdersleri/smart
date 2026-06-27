import math
import os
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core import metrics
from app.core.config import settings
from app.core.database import get_db
from app.core.timeutils import as_utc, utc_iso
from app.models.tag import Tag, TagReading
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def metrics_summary(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Poller/PLC sağlık metrikleri özeti (canlı izleme için JSON).

    PLC satırları, DB'deki tag kataloğundan PLC adı + yapılandırılmış tag sayısı
    ile zenginleştirilir (metrik label'ı yalnızca IP taşır).
    """
    data = metrics.summary()
    result = await db.execute(
        select(Tag.plc_ip, func.max(Tag.plc_name), func.count(Tag.id))
        .where(Tag.plc_ip.isnot(None))
        .group_by(Tag.plc_ip)
    )
    by_ip = {ip: {"name": name, "tag_count": cnt} for ip, name, cnt in result.all()}
    for p in data["plcs"]:
        info = by_ip.get(p["plc"], {})
        p["name"] = info.get("name")
        p["tag_count"] = info.get("tag_count", 0)
    return data


def compute_deadband_savings(items: list[dict]) -> dict:
    """Deadband ile önlenen yazma sayısını tahmin et.

    Her tag için beklenen satır = tag'in KENDİ etkin süresi (effective_seconds)
    / sample_interval; gerçek = DB'deki satır sayısı. Etkin süre, tag'in pencere
    içinde gerçekten veri ürettiği aralık (ilk→son kayıt) olduğundan, az yayılan
    veya hiç kaydı olmayan (effective=0) tag'ler sahte tasarruf üretmez.
    Tasarruf = beklenen - gerçek (negatif olmaz); oran toplam beklenene göre.
    """
    expected_total = 0
    actual_total = 0
    saved_total = 0
    for it in items:
        si = max(1, int(it["sample_interval"]))
        expected = max(0, int(it["effective_seconds"])) // si
        actual = int(it["actual"])
        expected_total += expected
        actual_total += actual
        saved_total += max(0, expected - actual)
    pct = round(saved_total / expected_total * 100, 1) if expected_total else None
    return {
        "deadband_tags": len(items),
        "expected_rows": expected_total,
        "actual_rows": actual_total,
        "saved_rows": saved_total,
        "savings_pct": pct,
    }


@router.get("/deadband_savings")
async def deadband_savings(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Deadband (report-by-exception) ile yapılan veri tasarrufunu dinamik hesapla.

    Yalnız deadband > 0 olan aktif uzun-süre tag'leri sayılır; son `hours`
    penceresindeki gerçek satır sayısı, deadband olmasaydı beklenen satır
    sayısıyla karşılaştırılır.
    """
    window_seconds = hours * 3600
    since = datetime.now(UTC) - timedelta(hours=hours)

    # Etkin toplama süresi PER-TAG hesaplanır: her tag'in beklenen satırı,
    # o tag'in pencere içinde GERÇEKTEN veri ürettiği aralığa (kendi ilk→son
    # kaydı, pencereyle sınırlı) göre belirlenir. Tek global span kullanmak,
    # az yayılan tag'leri şişirir ve pencerede hiç kaydı olmayan tag'lere sahte
    # "tasarruf" atfeder (collector kapalıyken geçen süre %99.9 gibi görünür).
    rows = await db.execute(
        select(
            Tag.id,
            Tag.sample_interval,
            func.count(TagReading.timestamp),
            func.min(TagReading.timestamp),
            func.max(TagReading.timestamp),
        )
        .outerjoin(
            TagReading,
            (TagReading.tag_id == Tag.id) & (TagReading.timestamp >= since),
        )
        .where(Tag.is_active, Tag.long_term, Tag.deadband.isnot(None), Tag.deadband > 0)
        .group_by(Tag.id, Tag.sample_interval)
    )
    items = []
    for _id, si, cnt, tmin, tmax in rows.all():
        span = int((tmax - tmin).total_seconds()) if tmin and tmax else 0
        items.append(
            {
                "sample_interval": si or 5,
                "actual": cnt,
                "effective_seconds": min(window_seconds, span),
            }
        )
    out = compute_deadband_savings(items)
    out["window_hours"] = hours
    # Temsili etkin süre = en uzun gözlem penceresi (gün ölçeklemesi için)
    rep_seconds = max((it["effective_seconds"] for it in items), default=0)
    out["effective_seconds"] = rep_seconds
    # Gözlenen tasarruf hızını tam güne ölçekle (kapasite planlama için)
    out["saved_rows_per_day"] = round(out["saved_rows"] * 86400 / rep_seconds) if rep_seconds else 0
    return out


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
        "last_reading": as_utc(last_reading),
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
            "timestamp": as_utc(r[6]),
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
    # also drop this tag from the user's watchlist groups
    member_ids = (
        (
            await db.execute(
                select(WatchlistGroupMember.id)
                .join(WatchlistGroup, WatchlistGroup.id == WatchlistGroupMember.group_id)
                .where(
                    WatchlistGroup.user_id == current_user.id, WatchlistGroupMember.tag_id == tag_id
                )
            )
        )
        .scalars()
        .all()
    )
    for mid in member_ids:
        m = await db.get(WatchlistGroupMember, mid)
        if m:
            await db.delete(m)
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
                "timestamp": as_utc(ts),
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


async def _raw_series(
    db: AsyncSession, tag_ids: list[int], since: datetime, max_points: int | None
) -> list[dict]:
    return await _raw_series_window(db, tag_ids, since, None, max_points)


async def _raw_series_window(
    db: AsyncSession,
    tag_ids: list[int],
    start: datetime,
    end: datetime | None,
    max_points: int | None,
) -> list[dict]:
    conditions = [Tag.id.in_(tag_ids), TagReading.timestamp >= start]
    if end is not None:
        conditions.append(TagReading.timestamp <= end)
    result = await db.execute(
        select(Tag.id, Tag.name, Tag.unit, TagReading.timestamp, TagReading.value)
        .join(TagReading, Tag.id == TagReading.tag_id)
        .where(*conditions)
        .order_by(TagReading.timestamp.asc())
    )
    series: dict[int, dict] = {}
    for tag_id, name, unit, ts, value in result.all():
        if tag_id not in series:
            series[tag_id] = {"tag_id": tag_id, "name": name, "unit": unit, "data": []}
        series[tag_id]["data"].append({"t": utc_iso(ts), "v": value})
    out = list(series.values())
    for s in out:
        s["data"] = downsample(s["data"], max_points)
    return out


# Pencere -> rollup view eşlemesi. None = ham veri (kısa pencere drill-down).
_ROLLUP_BY_HOURS = [(6, None), (48, "tag_readings_1m"), (168, "tag_readings_5m")]


def pick_rollup(hours: int) -> str | None:
    """İstenen pencereye uygun continuous-aggregate view'ını seç (yoksa ham)."""
    for limit, view in _ROLLUP_BY_HOURS:
        if hours <= limit:
            return view
    return "tag_readings_1h"


@router.get("/trend")
async def trend(
    tag_ids: list[int] = Query(...),
    hours: int = 24,
    max_points: int | None = Query(None, ge=2),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    return await _raw_series(db, tag_ids, since, max_points)


@router.get("/trend_range")
async def trend_range(
    tag_ids: list[int] = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
    max_points: int | None = Query(None, ge=2),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Açık başlangıç/bitiş penceresinde ham seri (dönem karşılaştırması için)."""
    s = start.replace(tzinfo=None) if start.tzinfo else start
    e = end.replace(tzinfo=None) if end.tzinfo else end
    return await _raw_series_window(db, tag_ids, s, e, max_points)


@router.get("/trend_agg")
async def trend_agg(
    tag_ids: list[int] = Query(...),
    hours: int = 24,
    max_points: int | None = Query(None, ge=2),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Pencereye göre rollup (continuous aggregate) çözünürlüğünden okur.

    Kısa pencere veya rollup yoksa (ör. SQLite dev) ham veriye düşer.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)
    view = pick_rollup(hours)
    if view is None:
        return await _raw_series(db, tag_ids, since, max_points)

    try:
        rows = (
            await db.execute(
                text(
                    f"SELECT r.tag_id, t.name, t.unit, r.bucket, r.avg "  # nosec B608 — {view} is a fixed rollup name from pick_rollup(); ids/since bound via bindparams
                    f"FROM {view} r JOIN tags t ON t.id = r.tag_id "
                    "WHERE r.tag_id = ANY(:ids) AND r.bucket >= :since "
                    "ORDER BY r.bucket ASC"
                ).bindparams(ids=tag_ids, since=since)
            )
        ).all()
    except Exception:
        await db.rollback()
        return await _raw_series(db, tag_ids, since, max_points)

    series: dict[int, dict] = {}
    for tag_id, name, unit, bucket, avg in rows:
        if tag_id not in series:
            series[tag_id] = {"tag_id": tag_id, "name": name, "unit": unit, "data": []}
        series[tag_id]["data"].append({"t": utc_iso(bucket), "v": avg})
    out = list(series.values())
    for s in out:
        s["data"] = downsample(s["data"], max_points)
    return out


# ---------------------------------------------------------------------------
# Database statistics
# ---------------------------------------------------------------------------

_DB_STAT_TABLES = [
    "tag_readings",
    "tags",
    "lab_measurements",
    "lab_samples",
    "report_history",
    "audit_logs",
    "app_settings",
]


def _sqlite_size_bytes(url: str) -> int:
    # sqlite+aiosqlite:///./scada_reporter.db  ->  ./scada_reporter.db
    path = url.split(":///")[-1]
    if not path or path == ":memory:":
        return 0
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


async def _table_count(db: AsyncSession, table: str) -> int:
    try:
        # nosec B608 - `table` is from the fixed _DB_STAT_TABLES allowlist, no user input
        result = await db.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        return int(result.scalar() or 0)
    except Exception:
        return 0  # table may not exist on an older schema


async def _total_readings(db: AsyncSession, url: str) -> tuple[int, bool]:
    """tag_readings satır sayısı. (count, is_exact) döner.

    SQLite (dev) küçük → tam `count(*)`. Postgres/TimescaleDB'de tablo on
    milyonlarca satır; tam count tam tarama yapar (saniyeler). Önce Timescale
    hypertable `approximate_row_count`, sonra planner `reltuples` tahminini
    dener — ikisi de anlık. Hiçbiri yoksa son çare tam count.
    """
    if url.startswith("sqlite"):
        total = int((await db.execute(text("SELECT count(*) FROM tag_readings"))).scalar() or 0)
        return total, True

    # Timescale hypertable: chunk istatistiklerinden anlık tahmin.
    try:
        est = (await db.execute(text("SELECT approximate_row_count('tag_readings')"))).scalar()
        if est is not None and int(est) > 0:
            return int(est), False
    except Exception:
        pass  # Timescale eklentisi yok ya da tablo hypertable değil

    # Postgres planner istatistiği (ANALYZE sonrası). -1 = hiç analiz edilmemiş.
    try:
        est = (
            await db.execute(
                text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'tag_readings'")
            )
        ).scalar()
        if est is not None and int(est) >= 0:
            return int(est), False
    except Exception:
        pass

    total = int((await db.execute(text("SELECT count(*) FROM tag_readings"))).scalar() or 0)
    return total, True


@router.get("/database")
async def database_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        size_bytes = _sqlite_size_bytes(url)
    else:
        size_bytes = int(
            (await db.execute(text("SELECT pg_database_size(current_database())"))).scalar() or 0
        )

    total, total_is_exact = await _total_readings(db, url)
    earliest = (await db.execute(text("SELECT min(timestamp) FROM tag_readings"))).scalar()

    now = datetime.utcnow()
    sql_recent = text("SELECT count(*) FROM tag_readings WHERE timestamp >= :c")
    last_day = int((await db.execute(sql_recent, {"c": now - timedelta(days=1)})).scalar() or 0)
    last_week = int((await db.execute(sql_recent, {"c": now - timedelta(days=7)})).scalar() or 0)
    last_month = int((await db.execute(sql_recent, {"c": now - timedelta(days=30)})).scalar() or 0)

    tag_count = int((await db.execute(text("SELECT count(*) FROM tags"))).scalar() or 0)

    tables = []
    for tbl in _DB_STAT_TABLES:
        tables.append({"name": tbl, "rows": await _table_count(db, tbl)})

    daily_rows = last_day
    est_monthly_growth = round((size_bytes / total) * daily_rows * 30) if total > 0 else 0

    return {
        "size_bytes": size_bytes,
        "total_readings": total,
        "total_is_estimate": not total_is_exact,
        "earliest": str(earliest) if earliest is not None else None,
        "last_day": last_day,
        "last_week": last_week,
        "last_month": last_month,
        "tag_count": tag_count,
        "tables": tables,
        "daily_rows": daily_rows,
        "est_monthly_growth_bytes": est_monthly_growth,
    }
