import os
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_restore_sqlite_overwrites_live(tmp_path):
    live = tmp_path / "live.db"
    _make_sqlite(str(live))  # 3 rows
    res = await be.create_snapshot(
        dest_dir=str(tmp_path / "bk"),
        db_url=f"sqlite+aiosqlite:///{live}",
        timestamp="20260627-031500",
    )
    # mutate live DB after snapshot
    con = sqlite3.connect(str(live))
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    assert sqlite3.connect(str(live)).execute("SELECT count(*) FROM t").fetchone()[0] == 0
    # restore brings back the 3 rows
    be.restore_snapshot(backup_path=res["path"], db_url=f"sqlite+aiosqlite:///{live}")
    assert sqlite3.connect(str(live)).execute("SELECT count(*) FROM t").fetchone()[0] == 3


def test_restore_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        be.restore_snapshot(
            backup_path=str(tmp_path / "nope.db"), db_url="sqlite+aiosqlite:///x.db"
        )


def test_expired_backup_ids():
    now = datetime(2026, 6, 27, tzinfo=UTC)
    rows = [
        SimpleNamespace(id=1, created_at=now - timedelta(days=400)),
        SimpleNamespace(id=2, created_at=now - timedelta(days=10)),
    ]
    assert be.expired_backup_ids(rows, retention_days=365, now_ts=now.timestamp()) == [1]
