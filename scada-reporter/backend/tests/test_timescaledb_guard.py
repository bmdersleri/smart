"""TimescaleDB init must skip cleanly on non-PostgreSQL dialects (e.g. SQLite dev).

On SQLite the Timescale-only DDL (CREATE EXTENSION / MATERIALIZED VIEW ...
timescaledb.continuous) can never succeed. Instead of attempting it and logging
scary WARNING / syntax-error noise every boot, the init functions short-circuit
on the dialect.
"""

from __future__ import annotations

import logging

import pytest

from app.core import timescaledb
from app.core.database import engine


@pytest.mark.asyncio
async def test_init_timescaledb_no_warning_on_sqlite(caplog):
    async with engine.begin() as conn:
        with caplog.at_level(logging.DEBUG, logger="app.core.timescaledb"):
            await timescaledb.init_timescaledb(conn)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


@pytest.mark.asyncio
async def test_init_continuous_aggregates_no_sql_noise_on_sqlite(caplog):
    async with engine.begin() as conn:
        with caplog.at_level(logging.DEBUG, logger="app.core.timescaledb"):
            await timescaledb.init_continuous_aggregates(conn)
    assert not any("syntax error" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_init_daily_rollup_no_sql_noise_on_sqlite(caplog):
    async with engine.begin() as conn:
        with caplog.at_level(logging.DEBUG, logger="app.core.timescaledb"):
            await timescaledb.init_daily_rollup(conn)
    assert not any("syntax error" in r.getMessage() for r in caplog.records)
