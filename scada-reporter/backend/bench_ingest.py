"""Real-Postgres ingest benchmark: INSERT vs COPY, and standalone-index cost.

Simulates the poller workload: T ticks x B rows/tick (one timestamp per tick,
B distinct tag_ids). Measures wall-clock + rows/sec for:
  - INSERT (SQLAlchemy executemany)  [old path / fallback / non-PG default]
  - COPY   (asyncpg copy_records_to_table)  [#1]
  - INSERT with the standalone ix_timestamp present  [shows #2's write cost]

Usage: python bench_ingest.py postgresql+asyncpg://postgres@localhost:5432/postgres
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

URL = sys.argv[1]
T = 100  # ticks
B = 3000  # rows per tick (full fleet)
BASE = datetime(2026, 1, 1, 0, 0, 0)  # naive UTC, like write_readings normalizes to

DDL_PLAIN = """
DROP TABLE IF EXISTS bench_readings;
CREATE TABLE bench_readings (
  tag_id integer NOT NULL,
  value double precision,
  quality integer DEFAULT 192,
  timestamp timestamp without time zone NOT NULL,
  PRIMARY KEY (tag_id, timestamp)
);
"""

INSERT_SQL = text(
    "INSERT INTO bench_readings (tag_id, value, quality, timestamp) "
    "VALUES (:tag_id, :value, :quality, :timestamp)"
)


def batch(tick: int):
    ts = BASE + timedelta(seconds=tick)
    return [
        {"tag_id": tid, "value": float(tid) + tick, "quality": 192, "timestamp": ts}
        for tid in range(1, B + 1)
    ]


async def reset(engine, *, with_index: bool):
    async with engine.begin() as c:
        for stmt in DDL_PLAIN.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
        if with_index:
            await c.execute(text("CREATE INDEX ix_bench_ts ON bench_readings (timestamp)"))


async def bench_insert(engine) -> float:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    t0 = time.perf_counter()
    for tick in range(T):
        async with sm() as db:
            # executemany INSERT — mirrors _insert_readings' bulk insert
            await db.execute(INSERT_SQL, batch(tick))
            await db.commit()
    return time.perf_counter() - t0


async def bench_copy(engine) -> float:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    t0 = time.perf_counter()
    for tick in range(T):
        ts = BASE + timedelta(seconds=tick)
        records = [(tid, float(tid) + tick, 192, ts) for tid in range(1, B + 1)]
        async with sm() as db:
            conn = await db.connection()
            raw = await conn.get_raw_connection()
            await raw.driver_connection.copy_records_to_table(
                "bench_readings",
                records=records,
                columns=["tag_id", "value", "quality", "timestamp"],
            )
            await db.commit()
    return time.perf_counter() - t0


async def main() -> int:
    engine = create_async_engine(URL)
    total = T * B

    await reset(engine, with_index=False)
    t_ins = await bench_insert(engine)

    await reset(engine, with_index=False)
    t_cpy = await bench_copy(engine)

    await reset(engine, with_index=True)
    t_ins_idx = await bench_insert(engine)

    await engine.dispose()

    print(f"rows total          : {total:,} ({T} ticks x {B} rows)")
    print(f"INSERT (no idx)     : {t_ins:7.3f}s  {total / t_ins:11,.0f} rows/s")
    print(f"COPY   (no idx)     : {t_cpy:7.3f}s  {total / t_cpy:11,.0f} rows/s")
    print(f"INSERT (+ ix_ts)    : {t_ins_idx:7.3f}s  {total / t_ins_idx:11,.0f} rows/s")
    print()
    print(f"#1 COPY vs INSERT   : {t_ins / t_cpy:5.2f}x faster")
    print(
        f"#2 idx write cost   : {(t_ins_idx - t_ins) / t_ins * 100:5.1f}% slower "
        f"INSERT with the redundant standalone timestamp index"
    )
    return 0


sys.exit(asyncio.run(main()))
