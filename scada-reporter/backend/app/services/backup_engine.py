"""Dialect-aware DB snapshot/restore. No FastAPI imports — pure service layer."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
from datetime import UTC


def sqlite_db_path(url: str) -> str | None:
    """Return the on-disk file path for a sqlite URL, else None."""
    if not url.startswith("sqlite"):
        return None
    # sqlite+aiosqlite:///./scada.db -> ./scada.db   (also handles absolute paths)
    tail = url.split(":///", 1)[-1]
    return os.path.abspath(tail)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_snapshot(path: str, dialect: str) -> bool:
    if not os.path.exists(path):
        return False
    if dialect == "sqlite":
        con = sqlite3.connect(path)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    # Postgres custom-format dumps are validated by pg_restore --list at restore time.
    return os.path.getsize(path) > 0


def _sqlite_vacuum_into(src_path: str, dest_path: str) -> None:
    """Consistent, WAL-safe, defragmented single-file snapshot."""
    con = sqlite3.connect(src_path)
    try:
        # VACUUM INTO requires the dest to NOT exist.
        if os.path.exists(dest_path):
            os.remove(dest_path)
        con.execute("VACUUM INTO ?", (dest_path,))
    finally:
        con.close()


async def _pg_dump(db_url: str, dest_path: str) -> None:
    """pg_dump custom format (-Fc): compressed, restorable with pg_restore."""
    # db_url: postgresql+asyncpg://user:pass@host:port/dbname -> libpq URL
    libpq = db_url.replace("postgresql+asyncpg", "postgresql").replace(
        "postgresql+psycopg", "postgresql"
    )
    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "-Fc",
        "-d",
        libpq,
        "-f",
        dest_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {err.decode(errors='replace')[:400]}")


async def create_snapshot(*, dest_dir: str, db_url: str, timestamp: str) -> dict:
    """Produce one snapshot file. `timestamp` supplied by caller (e.g. 20260627-031500)."""
    os.makedirs(dest_dir, exist_ok=True)
    sqlite_path = sqlite_db_path(db_url)

    if sqlite_path is not None:
        dialect = "sqlite"
        filename = f"backup-{timestamp}.db"
        dest = os.path.join(dest_dir, filename)
        await asyncio.to_thread(_sqlite_vacuum_into, sqlite_path, dest)
    else:
        dialect = "postgres"
        filename = f"backup-{timestamp}.dump"
        dest = os.path.join(dest_dir, filename)
        await _pg_dump(db_url, dest)

    if not verify_snapshot(dest, dialect):
        raise RuntimeError("integrity check failed on fresh snapshot")

    return {
        "filename": filename,
        "path": dest,
        "dialect": dialect,
        "size_bytes": os.path.getsize(dest),
        "sha256": await asyncio.to_thread(sha256_file, dest),
    }


def restore_snapshot(*, backup_path: str, db_url: str) -> None:
    """Restore a snapshot into the live DB.

    SQLite: copies backup pages into the live DB file via the sqlite3 online
    backup API (in-place overwrite, WAL-safe). Stop the collector/scheduler
    first to avoid concurrent writes racing the restore.

    Postgres: not automated here — restore a -Fc dump out-of-band with
    `pg_restore --clean --if-exists -d <url> <file>`.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(backup_path)

    live = sqlite_db_path(db_url)
    if live is None:
        raise NotImplementedError(
            "Automated restore supports SQLite only; use pg_restore for Postgres."
        )
    if not verify_snapshot(backup_path, "sqlite"):
        raise ValueError("backup failed integrity check; refusing to restore")

    src = sqlite3.connect(backup_path)
    dest = sqlite3.connect(live)
    try:
        src.backup(dest)  # online backup API: page-by-page copy into live db
        dest.commit()
    finally:
        dest.close()
        src.close()


def expired_backup_ids(rows: list, *, retention_days: int, now_ts: float) -> list[int]:
    cutoff = now_ts - retention_days * 86400
    out: list[int] = []
    for r in rows:
        created = r.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created.timestamp() < cutoff:
            out.append(r.id)
    return out
