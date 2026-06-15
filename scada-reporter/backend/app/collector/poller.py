import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.collector.s7_collector import collector
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tag import Tag, TagReading

logger = logging.getLogger(__name__)


async def poll_loop():
    """Aktif tag'leri periyodik olarak okur ve veritabanına yazar."""
    logger.info("Poller basliyor, interval: %ds", settings.S7_POLL_INTERVAL)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Tag).where(Tag.is_active))
                tags = result.scalars().all()

            if not tags:
                await asyncio.sleep(settings.S7_POLL_INTERVAL)
                continue

            addresses = [t.node_id for t in tags]
            tag_map = {t.node_id: t.id for t in tags}

            readings_data = await collector.read_tags_bulk(addresses)

            async with AsyncSessionLocal() as db:
                for address, value, quality, ts in readings_data:
                    db.add(
                        TagReading(
                            tag_id=tag_map[address],
                            value=value,
                            quality=quality,
                            timestamp=ts,
                        )
                    )
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()

            logger.debug("%d tag okundu", len(readings_data))

        except Exception as e:
            logger.error("Poll hatasi: %s", e)

        await asyncio.sleep(settings.S7_POLL_INTERVAL)
