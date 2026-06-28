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
    phases: list[str] = []
    res = await be.create_snapshot(
        dest_dir=str(dest),
        db_url=f"sqlite+aiosqlite:///{src}",
        timestamp="20260627-031500",
        progress_cb=lambda phase, frac: phases.append(phase),
    )
    assert res["dialect"] == "sqlite"
    # SQLite snapshots are zstd-compressed artifacts.
    assert res["filename"].endswith(".db.zst")
    assert os.path.exists(res["path"])
    assert res["size_bytes"] > 0
    assert len(res["sha256"]) == 64
    # progress callback fired through the expected phases
    assert {"vacuum", "compress", "hash", "done"} <= set(phases)
    # the temp uncompressed file is cleaned up
    assert not any(p.name.startswith(".tmp-") for p in dest.iterdir())
    # decompresses back into a valid, queryable sqlite db with the same rows
    restored = tmp_path / "restored.db"
    be._zstd_decompress(res["path"], str(restored))
    con = sqlite3.connect(str(restored))
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 3
    con.close()
    assert be.verify_snapshot(str(restored), "sqlite") is True


@pytest.mark.asyncio
async def test_zstd_compresses_below_raw(tmp_path):
    """A defragmented snapshot must be meaningfully smaller compressed than raw."""
    src = tmp_path / "live.db"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE big (id INTEGER PRIMARY KEY, v TEXT)")
    # Highly compressible repetitive payload.
    con.executemany("INSERT INTO big (v) VALUES (?)", [("x" * 200,) for _ in range(5000)])
    con.commit()
    con.close()
    raw = os.path.getsize(src)
    res = await be.create_snapshot(
        dest_dir=str(tmp_path / "bk"),
        db_url=f"sqlite+aiosqlite:///{src}",
        timestamp="20260627-031500",
    )
    assert res["size_bytes"] < raw * 0.5, f"compressed {res['size_bytes']} not < 50% of raw {raw}"


@pytest.mark.asyncio
async def test_restore_reports_progress(tmp_path):
    live = tmp_path / "live.db"
    _make_sqlite(str(live))
    res = await be.create_snapshot(
        dest_dir=str(tmp_path / "bk"),
        db_url=f"sqlite+aiosqlite:///{live}",
        timestamp="20260627-031500",
    )
    phases: list[str] = []
    be.restore_snapshot(
        backup_path=res["path"],
        db_url=f"sqlite+aiosqlite:///{live}",
        progress_cb=lambda phase, frac: phases.append(phase),
    )
    assert {"decompress", "restore", "done"} <= set(phases)


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


def test_verify_snapshot_missing_file():
    """#1: verify_snapshot must return False (not a false-positive 'ok') for a non-existent path."""
    assert be.verify_snapshot("/no/such/path.db", "sqlite") is False
