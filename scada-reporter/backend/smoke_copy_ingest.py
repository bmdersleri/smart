"""Throwaway smoke-test for poller COPY ingest against a REAL PostgreSQL.

Run against a temp PG cluster (see smoke orchestration). Validates the asyncpg
COPY machinery that has no automated coverage (dev = SQLite):
  1. clean batch  -> COPY writes all rows
  2. duplicate    -> unique_violation -> returns 0, no extra rows
  3. forced error -> non-23505 COPY failure falls back to INSERT (no data loss)

NOTE: plain PG table (no TimescaleDB hypertable here). Covers COPY mechanism,
txn/commit, conflict, tz, fallback — NOT hypertable/compressed-chunk routing.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime

os.environ["S7_PG_COPY_INGEST"] = "true"
os.environ["DATABASE_URL"] = sys.argv[1]  # postgresql+asyncpg://...

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.collector import poller  # noqa: E402
from app.models.tag import TagReading  # noqa: E402

DDL = """
DROP TABLE IF EXISTS tag_readings;
CREATE TABLE tag_readings (
  tag_id integer NOT NULL,
  value double precision,
  quality integer DEFAULT 192,
  timestamp timestamp without time zone NOT NULL,
  PRIMARY KEY (tag_id, timestamp)
);
"""


async def count(sm) -> int:
    async with sm() as s:
        return int(await s.scalar(select(func.count()).select_from(TagReading)) or 0)


async def main() -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        for stmt in DDL.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))

    failures: list[str] = []
    ts = datetime.now(UTC)  # tz-AWARE on purpose (poller passes aware)

    # 1. clean batch via COPY
    rows = [(1, 1.5, 192), (2, None, 0), (3, 9.9, 192)]
    n = await poller.write_readings(rows, ts, sessionmaker=sm)
    c1 = await count(sm)
    print(f"[1] clean COPY: returned={n} rows_in_db={c1}")
    if n != 3 or c1 != 3:
        failures.append("clean batch did not write 3 rows via COPY")
    # verify tz stored as naive UTC wall-clock + NULL value round-trips
    async with sm() as s:
        row = (
            await s.execute(text("SELECT value, timestamp FROM tag_readings WHERE tag_id=2"))
        ).first()
    print(f"[1b] tag_id=2 value={row[0]!r} ts={row[1]!r} (expect None + naive)")
    if row[0] is not None or row[1].tzinfo is not None:
        failures.append("NULL value or naive-ts round-trip wrong")

    # 2. duplicate batch -> unique_violation -> 0, no extra rows
    n2 = await poller.write_readings([(1, 5.0, 192)], ts, sessionmaker=sm)
    c2 = await count(sm)
    print(f"[2] duplicate COPY: returned={n2} rows_in_db={c2} (expect 0 / 3)")
    if n2 != 0 or c2 != 3:
        failures.append("duplicate batch did not return 0 / left extra rows")

    # 3. forced non-23505 COPY error -> fallback to INSERT (row lands)
    import asyncpg

    orig = asyncpg.Connection.copy_records_to_table

    async def boom(self, *a, **k):
        raise RuntimeError("forced COPY failure (no sqlstate)")

    asyncpg.Connection.copy_records_to_table = boom
    try:
        ts3 = datetime.now(UTC)
        n3 = await poller.write_readings([(99, 7.0, 192)], ts3, sessionmaker=sm)
    finally:
        asyncpg.Connection.copy_records_to_table = orig
    c3 = await count(sm)
    print(f"[3] forced-error fallback: returned={n3} rows_in_db={c3} (expect 1 / 4)")
    if n3 != 1 or c3 != 4:
        failures.append("forced COPY error did not fall back to INSERT")

    await engine.dispose()

    if failures:
        print("\nSMOKE FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nSMOKE OK: COPY write + NULL/tz round-trip + conflict->0 + error->INSERT fallback")
    return 0


sys.exit(asyncio.run(main()))
