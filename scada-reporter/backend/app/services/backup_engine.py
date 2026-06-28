"""Dialect-aware DB snapshot/restore. No FastAPI imports — pure service layer.

SQLite snapshots are zstd-compressed (`.db.zst`): a fresh VACUUM INTO file is
defragmented and full of zero pages, so it compresses heavily (often <15% of
the live DB). Postgres dumps stay `-Fc` (pg_dump's own compression).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC

import zstandard

# (phase, fraction 0..1) — phases: vacuum, verify, compress, hash, done,
# dump (pg); restore side: safety, decompress, restore.
ProgressCb = Callable[[str, float], None]


def _noop(_phase: str, _frac: float) -> None:
    return None


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


def _zstd_compress(src: str, dest: str, *, level: int, progress_cb: ProgressCb) -> None:
    """Stream-compress src -> dest with multithreaded zstd, reporting byte progress."""
    total = os.path.getsize(src) or 1
    cctx = zstandard.ZstdCompressor(level=level, threads=-1)
    done = 0
    with open(src, "rb") as fi, open(dest, "wb") as fo, cctx.stream_writer(fo) as comp:
        for chunk in iter(lambda: fi.read(1 << 20), b""):
            comp.write(chunk)
            done += len(chunk)
            progress_cb("compress", done / total)


def _zstd_decompress(src: str, dest: str) -> None:
    """Stream-decompress a .zst file back to a plain file."""
    dctx = zstandard.ZstdDecompressor()
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        dctx.copy_stream(fi, fo, read_size=1 << 20, write_size=1 << 20)


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


async def create_snapshot(
    *,
    dest_dir: str,
    db_url: str,
    timestamp: str,
    zstd_level: int = 19,
    progress_cb: ProgressCb | None = None,
) -> dict:
    """Produce one snapshot file. `timestamp` supplied by caller (e.g. 20260627-031500).

    SQLite path: VACUUM INTO a temp file -> integrity-check -> zstd-compress to
    `backup-<ts>.db.zst` -> sha256 the compressed artifact. The temp file is
    removed afterwards. `progress_cb(phase, fraction)` reports live progress.
    """
    cb = progress_cb or _noop
    os.makedirs(dest_dir, exist_ok=True)
    sqlite_path = sqlite_db_path(db_url)

    if sqlite_path is not None:
        dialect = "sqlite"
        filename = f"backup-{timestamp}.db.zst"
        dest = os.path.join(dest_dir, filename)
        tmp = os.path.join(dest_dir, f".tmp-{timestamp}.db")
        cb("vacuum", 0.0)
        await asyncio.to_thread(_sqlite_vacuum_into, sqlite_path, tmp)
        try:
            cb("verify", 0.0)
            if not verify_snapshot(tmp, "sqlite"):
                raise RuntimeError("integrity check failed on fresh snapshot")
            cb("compress", 0.0)
            await asyncio.to_thread(_zstd_compress, tmp, dest, level=zstd_level, progress_cb=cb)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    else:
        dialect = "postgres"
        filename = f"backup-{timestamp}.dump"
        dest = os.path.join(dest_dir, filename)
        cb("dump", 0.0)
        await _pg_dump(db_url, dest)
        if not verify_snapshot(dest, dialect):
            raise RuntimeError("integrity check failed on fresh snapshot")

    cb("hash", 0.0)
    sha = await asyncio.to_thread(sha256_file, dest)
    cb("done", 1.0)
    return {
        "filename": filename,
        "path": dest,
        "dialect": dialect,
        "size_bytes": os.path.getsize(dest),
        "sha256": sha,
    }


def restore_snapshot(
    *,
    backup_path: str,
    db_url: str,
    progress_cb: ProgressCb | None = None,
) -> None:
    """Restore a snapshot into the live DB.

    SQLite: a `.db.zst` artifact is stream-decompressed to a temp `.db` first,
    then its pages are copied into the live DB file via the sqlite3 online
    backup API (in-place overwrite, WAL-safe). Stop the collector/scheduler
    first to avoid concurrent writes racing the restore.

    Postgres: not automated here — restore a -Fc dump out-of-band with
    `pg_restore --clean --if-exists -d <url> <file>`.
    """
    cb = progress_cb or _noop
    if not os.path.exists(backup_path):
        raise FileNotFoundError(backup_path)

    live = sqlite_db_path(db_url)
    if live is None:
        raise NotImplementedError(
            "Automated restore supports SQLite only; use pg_restore for Postgres."
        )

    tmp: str | None = None
    src_db = backup_path
    if backup_path.endswith(".zst"):
        cb("decompress", 0.0)
        tmp = backup_path[: -len(".zst")] + ".restore-tmp"
        _zstd_decompress(backup_path, tmp)
        src_db = tmp
    try:
        cb("verify", 0.0)
        if not verify_snapshot(src_db, "sqlite"):
            raise ValueError("backup failed integrity check; refusing to restore")
        cb("restore", 0.0)
        src = sqlite3.connect(src_db)
        dest = sqlite3.connect(live)
        try:
            src.backup(dest)  # online backup API: page-by-page copy into live db
            dest.commit()
        finally:
            dest.close()
            src.close()
        cb("done", 1.0)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)


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
