"""Dialect-aware DB snapshot/restore. No FastAPI imports — pure service layer."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3


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
    if dialect == "sqlite":
        con = sqlite3.connect(path)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    # Postgres custom-format dumps are validated by pg_restore --list at restore time.
    return os.path.exists(path) and os.path.getsize(path) > 0


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
