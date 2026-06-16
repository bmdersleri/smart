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


# Sürekli toplama (continuous aggregate) rollup'ları: trend sorguları pencereye
# göre uygun çözünürlükten okur; ham veri drill-down için kalır.
# (bucket, avg/min/max/count). Politikalar düzenli tazeler.
CAGGS = [
    ("tag_readings_1m", "1 minute", "3 hours", "1 minute", "1 minute"),
    ("tag_readings_5m", "5 minutes", "1 day", "5 minutes", "5 minutes"),
    ("tag_readings_1h", "1 hour", "7 days", "1 hour", "30 minutes"),
]


async def init_continuous_aggregates(conn: AsyncConnection) -> None:
    """TimescaleDB sürekli toplama view'larını + tazeleme politikalarını kur.

    AUTOCOMMIT bağlantısı bekler (CAGG DDL açık transaction içinde çalışmaz).
    Timescale yoksa (ör. SQLite dev) sessizce atlanır.
    """
    for view, bucket, start_off, end_off, sched in CAGGS:
        try:
            await conn.execute(
                text(
                    f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view} "
                    "WITH (timescaledb.continuous) AS "
                    f"SELECT tag_id, time_bucket(INTERVAL '{bucket}', timestamp) AS bucket, "
                    "avg(value) AS avg, min(value) AS min, max(value) AS max, count(*) AS n "
                    "FROM tag_readings GROUP BY tag_id, bucket WITH NO DATA"
                )
            )
            await conn.execute(
                text(
                    f"SELECT add_continuous_aggregate_policy('{view}', "
                    f"start_offset => INTERVAL '{start_off}', "
                    f"end_offset => INTERVAL '{end_off}', "
                    f"schedule_interval => INTERVAL '{sched}', if_not_exists => TRUE)"
                )
            )
            logger.info("Continuous aggregate ready: %s (%s)", view, bucket)
        except Exception as e:
            logger.info("Continuous aggregate skipped/exists: %s - %s", view, e)


async def init_daily_rollup(conn: AsyncConnection) -> None:
    """Uzun saklamalı günlük toplama (rapor şablonları için).

    avg/min/max/sum/first/last/count saklar. Retention YOK — yıllarca tutulur.
    first/last bir Timescale sürümünde reddedilirse hata loglanıp atlanır;
    o durumda last/delta yalnız SQLite/dev'de hesaplanabilir.
    """
    try:
        await conn.execute(
            text(
                "CREATE MATERIALIZED VIEW IF NOT EXISTS tag_readings_1d "
                "WITH (timescaledb.continuous) AS "
                "SELECT tag_id, time_bucket(INTERVAL '1 day', timestamp) AS bucket, "
                "avg(value) AS avg, min(value) AS min, max(value) AS max, "
                "sum(value) AS sum, count(*) AS n, "
                "first(value, timestamp) AS first_v, last(value, timestamp) AS last_v "
                "FROM tag_readings GROUP BY tag_id, bucket WITH NO DATA"
            )
        )
        await conn.execute(
            text(
                "SELECT add_continuous_aggregate_policy('tag_readings_1d', "
                "start_offset => INTERVAL '7 days', "
                "end_offset => INTERVAL '1 hour', "
                "schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
            )
        )
        logger.info("Daily rollup ready: tag_readings_1d (no retention)")
    except Exception as e:
        logger.info("Daily rollup skipped/exists: %s", e)
