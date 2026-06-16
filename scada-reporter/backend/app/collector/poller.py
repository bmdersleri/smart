"""Çoklu-PLC poller.

Aktif tag'leri PLC'ye göre gruplar, her PLC'yi kendi bağlantısından okur,
PLC'ler arası eşzamanlı (asyncio.gather), her tag kendi sample_interval'ında.
"""

import asyncio
import logging
import math
import time
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.collector.s7_collector import BAD, ReadSpec, parse_address, plc_manager
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tag import Tag, TagReading

logger = logging.getLogger(__name__)


async def read_plc_group(
    key: tuple[str, int, int],
    items: list[tuple[int, ReadSpec]],
    timeout: float,
) -> list[tuple[int, float | None, int]]:
    """Bir PLC grubunu zaman aşımı sınırıyla oku. Hata/zaman aşımı -> hepsi BAD."""
    ip, rack, slot = key
    specs = [spec for _, spec in items]
    try:
        results = await asyncio.wait_for(
            plc_manager.read_plc_batch(ip, rack, slot, specs), timeout=timeout
        )
    except Exception as e:
        logger.warning("PLC grup okuma hatasi/zaman asimi %s: %s", ip, e)
        results = [(None, BAD)] * len(specs)
    return [
        (tag_id, value, quality)
        for (tag_id, _), (value, quality) in zip(items, results, strict=False)
    ]


async def poll_loop() -> None:
    """Aktif tag'leri periyodik okur ve veritabanına yazar (çoklu PLC)."""
    logger.info("Poller basliyor (coklu PLC), tick alt siniri: %ds", settings.S7_POLL_INTERVAL)
    last_read: dict[int, float] = {}

    while True:
        tick_start = time.monotonic()
        min_interval = settings.S7_POLL_INTERVAL
        try:
            async with AsyncSessionLocal() as db:
                # Sadece uzun-süre (archive) tag'leri topla/kaydet
                result = await db.execute(select(Tag).where(Tag.is_active, Tag.long_term))
                tags = result.scalars().all()

            now = time.monotonic()
            # PLC'ye (ip,rack,slot) göre grupla; sadece zamanı gelmiş + adresi olanlar
            groups: dict[tuple[str, int, int], list[tuple[int, ReadSpec]]] = defaultdict(list)
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
                groups[(t.plc_ip, t.plc_rack, t.plc_slot)].append((t.id, spec))

            async def read_group(
                key: tuple[str, int, int],
                items: list[tuple[int, ReadSpec]],
                stamp: float = now,
            ) -> list[tuple[int, float | None, int]]:
                ip, rack, slot = key
                specs = [spec for _, spec in items]
                results = await plc_manager.read_plc_batch(ip, rack, slot, specs)
                out: list[tuple[int, float | None, int]] = []
                for (tag_id, _), (value, quality) in zip(items, results, strict=False):
                    last_read[tag_id] = stamp
                    out.append((tag_id, value, quality))
                return out

            rows: list[tuple[int, float | None, int]] = []
            if groups:
                batches = await asyncio.gather(
                    *(read_group(k, v) for k, v in groups.items()),
                    return_exceptions=True,
                )
                for b in batches:
                    if isinstance(b, BaseException):
                        logger.warning("PLC batch hatasi: %s", b)
                        continue
                    rows.extend(b)

            if rows:
                ts = datetime.now(UTC)
                async with AsyncSessionLocal() as db:
                    for tag_id, value, quality in rows:
                        db.add(
                            TagReading(tag_id=tag_id, value=value, quality=quality, timestamp=ts)
                        )
                    try:
                        await db.commit()
                    except IntegrityError:
                        await db.rollback()
                logger.debug("%d tag okundu (%d PLC)", len(rows), len(groups))

        except Exception as e:
            logger.error("Poll hatasi: %s", e)

        tick = max(1, min_interval)
        elapsed = time.monotonic() - tick_start
        await asyncio.sleep(max(0.0, tick - elapsed))
