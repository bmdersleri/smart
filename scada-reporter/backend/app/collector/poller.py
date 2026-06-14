import asyncio
import logging
from sqlalchemy import select
from app.collector.opc_client import collector
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.tag import Tag, TagReading
from datetime import datetime

logger = logging.getLogger(__name__)


async def poll_loop():
    """Aktif tag'leri periyodik olarak okur ve veritabanına yazar."""
    logger.info("Poller basliyor, interval: %ds", settings.OPC_UA_POLL_INTERVAL)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Tag).where(Tag.is_active == True))
                tags = result.scalars().all()

            if not tags:
                await asyncio.sleep(settings.OPC_UA_POLL_INTERVAL)
                continue

            node_ids = [t.node_id for t in tags]
            tag_map = {t.node_id: t.id for t in tags}

            readings_data = await collector.read_tags_bulk(node_ids)

            async with AsyncSessionLocal() as db:
                for node_id, value, quality, ts in readings_data:
                    reading = TagReading(
                        tag_id=tag_map[node_id],
                        value=value,
                        quality=quality,
                        timestamp=ts,
                    )
                    db.add(reading)
                await db.commit()

            logger.debug("%d tag okundu", len(readings_data))

        except Exception as e:
            logger.error("Poll hatasi: %s", e)

        await asyncio.sleep(settings.OPC_UA_POLL_INTERVAL)
