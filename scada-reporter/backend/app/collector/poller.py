"""Çoklu-PLC poller.

Aktif (long_term) tag'leri PLC'ye göre gruplar, her PLC'yi kendi bağlantısından
blok okur, PLC'ler arası eşzamanlı (asyncio.gather), her tag kendi
sample_interval'ında. Son değerler latest_cache'e, geçmiş tag_readings'e yazılır.
"""

import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.collector.cache import latest_cache
from app.collector.plc_health_tracker import health_tracker
from app.collector.s7_collector import BAD, GOOD, ReadSpec, parse_address, plc_manager
from app.core import metrics
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tag import Tag, TagReading

logger = logging.getLogger(__name__)

Batch = tuple[datetime, list[tuple[int, float | None, int]]]


class WriteBuffer:
    """DB blip'inde düşen tick'leri tutan sınırlı tampon (backpressure).

    Dolunca en eski batch düşer (bounded deque). Bir sonraki başarılı tick'te
    flush edilir → geçici DB kesintilerinde veri kaybını önler.
    """

    def __init__(self, maxlen: int = 60) -> None:
        self._q: deque[Batch] = deque(maxlen=maxlen)

    def add(self, ts: datetime, rows: list[tuple[int, float | None, int]]) -> None:
        self._q.append((ts, rows))

    def drain(self) -> list[Batch]:
        items = list(self._q)
        self._q.clear()
        return items

    def __len__(self) -> int:
        return len(self._q)


write_buffer = WriteBuffer()


class TagCache:
    """Aktif (long_term) tag listesini TTL ile tutar.

    Her tick'te DB'den ~3000 satır çekmek yerine, liste `ttl` saniye boyunca
    yeniden kullanılır. Tag CRUD değişiklikleri en geç TTL kadar gecikmeyle
    poller'a yansır. Tag nesneleri okunduğu session kapandıktan sonra detached
    olur; tüm kolon değerleri select ile yüklü olduğundan tick'ler arası
    yeniden kullanım güvenli (DB'ye dönmez).
    """

    def __init__(self, ttl: float | None = None) -> None:
        self.ttl = settings.S7_TAG_CACHE_TTL if ttl is None else ttl
        self._tags: list[Tag] | None = None
        self._fetched_at: float = -math.inf

    def fresh(self, now: float) -> bool:
        return self._tags is not None and (now - self._fetched_at) < self.ttl

    def store(self, tags: list[Tag], now: float) -> None:
        self._tags = tags
        self._fetched_at = now

    @property
    def tags(self) -> list[Tag]:
        return self._tags or []

    def invalidate(self) -> None:
        self._tags = None
        self._fetched_at = -math.inf


tag_cache = TagCache()


async def read_plc_group(
    key: tuple[str, int, int],
    items: list[tuple[int, ReadSpec]],
    timeout: float,
    name: str = "",
) -> list[tuple[int, float | None, int]]:
    """Bir PLC grubunu zaman aşımı sınırıyla oku. Hata/zaman aşımı -> hepsi BAD."""
    ip, rack, slot = key
    specs = [spec for _, spec in items]
    read_start = time.monotonic()
    read_error: str | None = None
    try:
        results = await asyncio.wait_for(
            plc_manager.read_plc_batch(ip, rack, slot, specs), timeout=timeout
        )
    except Exception as e:
        logger.warning("PLC grup okuma hatasi/zaman asimi %s: %s", ip, e)
        results = [(None, BAD)] * len(specs)
        # asyncio.TimeoutError str()'i boş; tip adına düş
        read_error = str(e) or e.__class__.__name__
    finally:
        metrics.observe_plc_read(ip, time.monotonic() - read_start)
    rows = [
        (tag_id, value, quality)
        for (tag_id, _), (value, quality) in zip(items, results, strict=False)
    ]
    good = sum(1 for _, _, q in rows if q == GOOD)
    bad = len(rows) - good
    health_tracker.record_read(key, name, good, bad, time.monotonic(), error=read_error)
    return rows


def should_store(
    tag_id: int,
    value: float | None,
    quality: int,
    *,
    now: float,
    last_stored: dict[int, tuple[float | None, int, float]],
    deadband: float | None,
    heartbeat: float,
) -> bool:
    """Report-by-exception: deadband içinde kalan değişmemiş değeri DB'ye yazma.

    İlk okuma, kalite değişimi, heartbeat aşımı veya deadband'ı aşan hareket
    -> yaz. deadband None/0 ise her zaman yaz (eski davranış).
    """
    prev = last_stored.get(tag_id)
    if prev is None:
        return True
    prev_value, prev_quality, prev_ts = prev
    if quality != prev_quality:
        return True
    if now - prev_ts >= heartbeat:
        return True
    if not deadband:
        return True
    if value is None or prev_value is None:
        return True
    return abs(value - prev_value) >= deadband


async def _insert_readings(db, rows: list[tuple[int, float | None, int]], ts: datetime) -> int:
    """Tek bulk INSERT. Çakışmada (PK) tüm batch geri alınır, 0 döner."""
    payload = [
        {"tag_id": tag_id, "value": value, "quality": quality, "timestamp": ts}
        for tag_id, value, quality in rows
    ]
    try:
        await db.execute(insert(TagReading), payload)
        await db.commit()
        return len(payload)
    except IntegrityError:
        await db.rollback()
        return 0


async def _copy_readings(db, rows: list[tuple[int, float | None, int]], ts: datetime) -> int:
    """PostgreSQL asyncpg COPY ile bulk ingest (INSERT'ten ~3-10x hızlı).

    Çakışma (unique_violation, sqlstate 23505) → batch geri alınır, 0 döner
    (INSERT semantiği ile aynı). Başka herhangi bir COPY hatası (sürüm/driver)
    → veri kaybı olmaması için INSERT'e düşülür.
    """
    records = [(tag_id, value, quality, ts) for tag_id, value, quality in rows]
    try:
        conn = await db.connection()
        raw = await conn.get_raw_connection()
        asyncpg_conn = raw.driver_connection
        await asyncpg_conn.copy_records_to_table(
            "tag_readings",
            records=records,
            columns=["tag_id", "value", "quality", "timestamp"],
        )
        await db.commit()
        return len(records)
    except Exception as exc:
        await db.rollback()
        if getattr(exc, "sqlstate", None) == "23505":  # unique_violation
            return 0
        logger.warning("PG COPY ingest hatasi (%s); INSERT'e dusuluyor", exc.__class__.__name__)
        return await _insert_readings(db, rows, ts)


async def write_readings(
    rows: list[tuple[int, float | None, int]],
    ts: datetime,
    sessionmaker=AsyncSessionLocal,
) -> int:
    """rows'u tek bulk yazımla kaydet. PG'de COPY, değilse INSERT. Çakışmada 0."""
    if not rows:
        return 0
    # tag_readings.timestamp = "timestamp without time zone". Hem asyncpg INSERT
    # hem raw COPY, tz-aware datetime'ı bu kolona reddeder ("can't subtract
    # offset-naive and offset-aware"). Poller UTC-aware ts geçer → naive UTC'ye
    # normalize et (gerçek-PG smoke testinde yakalandı; SQLite gizliyordu).
    ts = ts.replace(tzinfo=None) if ts.tzinfo else ts
    async with sessionmaker() as db:
        if settings.S7_PG_COPY_INGEST and db.bind.dialect.name == "postgresql":
            return await _copy_readings(db, rows, ts)
        return await _insert_readings(db, rows, ts)


async def run_once(
    last_read: dict[int, float],
    *,
    now: float,
    sessionmaker=AsyncSessionLocal,
    timeout: float | None = None,
    last_stored: dict[int, tuple[float | None, int, float]] | None = None,
    buffer: WriteBuffer | None = None,
    cache: TagCache | None = None,
) -> tuple[int, int]:
    """Bir tick: due tag'leri oku, cache + DB'ye yaz. (yazılan_satır, min_interval).

    last_stored verilirse deadband (report-by-exception) uygulanır: değişmeyen
    değerler DB'ye yazılmaz (cache yine güncellenir). None ise tüm satırlar yazılır.
    buffer verilirse DB yazma hatası satırları düşürmek yerine tamponlar; bir
    sonraki tick'te flush edilir (backpressure).
    cache verilirse aktif tag listesi TTL boyunca yeniden kullanılır (her tick
    DB sorgusunu önler). None ise her çağrıda taze çekilir (eski davranış).
    """
    timeout = settings.S7_PLC_READ_TIMEOUT if timeout is None else timeout

    if cache is not None and cache.fresh(now):
        tags = cache.tags
    else:
        async with sessionmaker() as db:
            result = await db.execute(select(Tag).where(Tag.is_active, Tag.long_term))
            tags = list(result.scalars().all())
        if cache is not None:
            cache.store(tags, now)

    min_interval = settings.S7_POLL_INTERVAL
    deadband_by_tag: dict[int, float | None] = {}
    groups: dict[tuple[str, int, int], list[tuple[int, ReadSpec]]] = defaultdict(list)
    group_name: dict[tuple[str, int, int], str] = {}
    for t in tags:
        if not t.s7_address or not t.plc_ip:
            continue
        interval = t.sample_interval or settings.S7_POLL_INTERVAL
        min_interval = min(min_interval, interval)
        if now - last_read.get(t.id, -math.inf) < interval:
            continue
        try:
            spec = parse_address(t.s7_address, t.data_type)
        except ValueError as e:
            logger.warning("Tag %s adres hatasi: %s", t.id, e)
            continue
        deadband_by_tag[t.id] = t.deadband
        key = (t.plc_ip, t.plc_rack, t.plc_slot)
        groups[key].append((t.id, spec))
        if t.plc_name:
            group_name[key] = t.plc_name

    rows: list[tuple[int, float | None, int]] = []
    if groups:
        batches = await asyncio.gather(
            *(read_plc_group(k, v, timeout, name=group_name.get(k, "")) for k, v in groups.items()),
            return_exceptions=True,
        )
        for b in batches:
            if isinstance(b, BaseException):
                logger.warning("PLC batch hatasi: %s", b)
                continue
            rows.extend(b)

    for tag_id, _, _ in rows:
        last_read[tag_id] = now

    if not rows:
        return 0, min_interval

    ts = datetime.now(UTC)
    latest_cache.update_many(rows, ts)  # cache her zaman taze değeri taşır

    if last_stored is None:
        store_rows = rows
    else:
        heartbeat = settings.S7_STORE_HEARTBEAT_SECONDS
        store_rows = [
            (tag_id, value, quality)
            for tag_id, value, quality in rows
            if should_store(
                tag_id,
                value,
                quality,
                now=now,
                last_stored=last_stored,
                deadband=deadband_by_tag.get(tag_id),
                heartbeat=heartbeat,
            )
        ]
        for tag_id, value, quality in store_rows:
            last_stored[tag_id] = (value, quality, now)

    metrics.add_bad_quality(sum(1 for _, _, q in rows if q == BAD))

    if buffer is None:
        written = await write_readings(store_rows, ts, sessionmaker=sessionmaker)
        metrics.add_rows_written(written)
        return written, min_interval

    # Backpressure: önce tamponlanmış batch'ler, sonra bu tick. İlk hatada
    # kalan tüm batch'ler yeniden tamponlanır (sıra korunur).
    pending = buffer.drain()
    pending.append((ts, store_rows))
    written = 0
    failed_from: int | None = None
    for i, (bts, brows) in enumerate(pending):
        try:
            written += await write_readings(brows, bts, sessionmaker=sessionmaker)
        except Exception as e:
            logger.warning("DB yazma hatasi, tamponlaniyor: %s", e)
            failed_from = i
            break
    if failed_from is not None:
        for bts, brows in pending[failed_from:]:
            buffer.add(bts, brows)
    metrics.add_rows_written(written)
    return written, min_interval


async def poll_loop() -> None:
    """Aktif tag'leri periyodik okur ve veritabanına + cache'e yazar (çoklu PLC)."""
    logger.info(
        "Poller basliyor (coklu PLC, blok okuma), tick alt siniri: %ds",
        settings.S7_POLL_INTERVAL,
    )
    last_read: dict[int, float] = {}
    last_stored: dict[int, tuple[float | None, int, float]] = {}
    while True:
        tick_start = time.monotonic()
        min_interval = settings.S7_POLL_INTERVAL
        try:
            _, min_interval = await run_once(
                last_read,
                now=time.monotonic(),
                last_stored=last_stored,
                buffer=write_buffer,
                cache=tag_cache,
            )
        except Exception as e:
            logger.error("Poll hatasi: %s", e)
        tick = max(1, min_interval)
        elapsed = time.monotonic() - tick_start
        metrics.observe_tick(elapsed)
        await asyncio.sleep(max(0.0, tick - elapsed))
