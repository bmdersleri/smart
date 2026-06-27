import os
import sqlite3

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.backup import Backup
from app.services import backup_engine as be


def test_backup_settings_have_defaults():
    assert isinstance(settings.BACKUP_DIR, str) and settings.BACKUP_DIR
    assert settings.BACKUP_RETENTION_DAYS > 0
    assert settings.BACKUP_SCHEDULE_CRON.count(" ") == 4  # 5-field cron
    assert isinstance(settings.RUN_BACKUP_SCHEDULER, bool)


@pytest.mark.asyncio
async def test_backup_model_persists(db_session):
    rec = Backup(
        filename="b.db",
        path="/x/b.db",
        dialect="sqlite",
        kind="full",
        status="completed",
        trigger="manual",
        size_bytes=10,
        sha256="abc",
    )
    db_session.add(rec)
    await db_session.commit()
    got = (await db_session.execute(select(Backup))).scalars().all()
    assert len(got) == 1 and got[0].sha256 == "abc"


def _make_sqlite(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)])
    con.commit()
    con.close()


def test_sqlite_db_path_parses_url():
    assert be.sqlite_db_path("sqlite+aiosqlite:///./scada.db").endswith("scada.db")
    assert be.sqlite_db_path("postgresql+asyncpg://u@h/db") is None


@pytest.mark.asyncio
async def test_create_snapshot_sqlite(tmp_path):
    src = tmp_path / "live.db"
    _make_sqlite(str(src))
    dest = tmp_path / "backups"
    res = await be.create_snapshot(
        dest_dir=str(dest),
        db_url=f"sqlite+aiosqlite:///{src}",
        timestamp="20260627-031500",
    )
    assert res["dialect"] == "sqlite"
    assert os.path.exists(res["path"])
    assert res["size_bytes"] > 0
    assert len(res["sha256"]) == 64
    # snapshot is a valid, queryable sqlite db with the same rows
    con = sqlite3.connect(res["path"])
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 3
    con.close()
    assert be.verify_snapshot(res["path"], "sqlite") is True
