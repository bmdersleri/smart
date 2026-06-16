import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings

logger = logging.getLogger(__name__)


async def init_timescaledb(conn: AsyncConnection):
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        logger.info("TimescaleDB extension ready")
    except Exception as e:
        logger.warning("TimescaleDB extension could not be created: %s", e)
        return

    tables = ["tag_readings"]
    for table in tables:
        try:
            await conn.execute(
                text(
                    "SELECT create_hypertable(:table, 'timestamp',"
                    " if_not_exists => TRUE, migrate_data => TRUE)"
                ).bindparams(table=table)
            )
            logger.info("Hypertable created: %s", table)
        except Exception as e:
            logger.info("Hypertable already exists or failed: %s - %s", table, e)

        try:
            await conn.execute(text(f"ALTER TABLE {table} SET (timescaledb.compress)"))
            logger.info("Compression enabled: %s", table)
        except Exception as e:
            logger.info("Compression already set: %s - %s", table, e)

        try:
            await conn.execute(
                text(
                    "SELECT add_compression_policy(:table,"
                    " INTERVAL '7 days', if_not_exists => TRUE)"
                ).bindparams(table=table)
            )
            logger.info("Compression policy added: %s", table)
        except Exception as e:
            logger.info("Compression policy exists: %s - %s", table, e)

        try:
            await conn.execute(
                text(
                    "SELECT add_retention_policy(:table,"
                    f" INTERVAL '{settings.RAW_RETENTION_DAYS} days', if_not_exists => TRUE)"
                ).bindparams(table=table)
            )
            logger.info("Retention policy added: %s (%d gün)", table, settings.RAW_RETENTION_DAYS)
        except Exception as e:
            logger.info("Retention policy exists: %s - %s", table, e)
