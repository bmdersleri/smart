# DB Backup & Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an application-managed database backup/restore feature — scheduled + on-demand snapshots, integrity-verified, admin-controlled, surfaced in Settings UI — closing the project's most critical gap (no backups exist today).

**Architecture:** A dialect-aware `BackupEngine` service produces a single-file consistent snapshot (SQLite `VACUUM INTO` for dev; `pg_dump` custom-format for Postgres/Timescale), records metadata (path, size, sha256, status) in a new `backups` table, and verifies integrity after every run. A FastAPI router (admin + writable gated) exposes create/list/download/delete/restore. An APScheduler cron job runs nightly backups + prunes by retention. The frontend adds a `SettingsBackupCard` (admin-only) plus a "last backup" health line.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, APScheduler (AsyncIOScheduler, already wired), Alembic, Pydantic v2, React 19 + TanStack/axios + Tailwind.

## Global Constraints

- Backend root: `C:\project\smart\scada-reporter\backend` — all backend paths below are relative to this.
- Frontend root: `C:\project\smart\scada-reporter\frontend`.
- Python interpreter is `python` (not `python3`) on Windows. Tests run via `just test` (pytest, parallel + randomized). Run a single test with `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest <path>::<name> -p no:randomly -n0 -v`.
- Alembic current head: `b2c3d4e5f6a8` — the new migration's `down_revision` MUST be `"b2c3d4e5f6a8"`.
- Mutating endpoints MUST gate on BOTH `Depends(require_role("admin"))` and `Depends(require_writable)` (demo mode is read-only). Reuse existing deps; do not invent new ones.
- Test DB isolation: tests share one in-memory SQLite engine (StaticPool); an autouse fixture clears tables before each test. Do not rely on cross-test data.
- Follow existing patterns verbatim: model style `app/models/report_archive.py`, router style `app/api/reports.py`, scheduler style `app/services/scheduler.py`, config style `app/core/config.py`, frontend card style `frontend/src/pages/SettingsRuntimeCard.tsx`.
- Scope: this plan delivers the SQLite path end-to-end (working dev deliverable) and the Postgres `pg_dump` path behind the same interface. Physical PITR (pgBackRest/WAL-G) is a SEPARATE infra plan — out of scope here.

---

## File Structure

**Create:**
- `app/models/backup.py` — `Backup` SQLAlchemy model.
- `app/services/backup_engine.py` — dialect-aware snapshot/restore/verify logic (no FastAPI imports).
- `app/api/backup.py` — router: create/list/download/delete/restore + schemas.
- `alembic/versions/c3d4e5f6a7b8_backups_table.py` — migration.
- `tests/test_backup_engine.py` — engine unit tests (SQLite).
- `tests/test_backup_api.py` — API + gating tests.
- `frontend/src/pages/SettingsBackupCard.tsx` — admin card.

**Modify:**
- `app/core/config.py` — add `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_SCHEDULE_CRON`, `RUN_BACKUP_SCHEDULER`.
- `alembic/env.py` — register `app.models.backup`.
- `app/main.py` — `include_router(backup.router, prefix="/api")`.
- `app/services/scheduler.py` — register nightly backup job + retention prune.
- `frontend/src/api/client.ts` — backup API functions.
- `frontend/src/pages/Settings.tsx` — mount `SettingsBackupCard`.
- `frontend/src/i18n/*` (or wherever strings live) — backup labels.

---

### Task 1: Config fields for backup

**Files:**
- Modify: `app/core/config.py` (Settings class, near `RUN_SCHEDULER`)
- Test: `tests/test_backup_engine.py` (new file — first assertion only)

**Interfaces:**
- Produces: `settings.BACKUP_DIR: str`, `settings.BACKUP_RETENTION_DAYS: int`, `settings.BACKUP_SCHEDULE_CRON: str`, `settings.RUN_BACKUP_SCHEDULER: bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backup_engine.py`:

```python
from app.core.config import settings


def test_backup_settings_have_defaults():
    assert isinstance(settings.BACKUP_DIR, str) and settings.BACKUP_DIR
    assert settings.BACKUP_RETENTION_DAYS > 0
    assert settings.BACKUP_SCHEDULE_CRON.count(" ") == 4  # 5-field cron
    assert isinstance(settings.RUN_BACKUP_SCHEDULER, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py::test_backup_settings_have_defaults -p no:randomly -n0 -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'BACKUP_DIR'`

- [ ] **Step 3: Add the settings fields**

In `app/core/config.py`, immediately after the `RUN_SCHEDULER: bool = True` line, add:

```python
    # --- Backup ---
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAYS: int = 365
    BACKUP_SCHEDULE_CRON: str = "0 3 * * *"  # daily 03:00, 5-field cron (m h dom mon dow)
    RUN_BACKUP_SCHEDULER: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py::test_backup_settings_have_defaults -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/config.py scada-reporter/backend/tests/test_backup_engine.py
git commit -m "feat(backup): add backup config settings"
```

---

### Task 2: Backup model + migration

**Files:**
- Create: `app/models/backup.py`
- Modify: `alembic/env.py` (model registry imports block, lines ~8-21)
- Create: `alembic/versions/c3d4e5f6a7b8_backups_table.py`
- Test: `tests/test_backup_engine.py`

**Interfaces:**
- Produces: `Backup` model with columns
  `id: int (pk)`, `filename: str`, `path: str`, `dialect: str`, `kind: str` (`"full"`),
  `status: str` (`pending|running|completed|failed|verified`), `trigger: str` (`manual|scheduled`),
  `size_bytes: int|None`, `sha256: str|None`, `error: str|None`,
  `created_at: datetime`, `completed_at: datetime|None`, `triggered_by: int|None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backup_engine.py`:

```python
import pytest
from sqlalchemy import select
from app.models.backup import Backup


@pytest.mark.asyncio
async def test_backup_model_persists(db_session):
    rec = Backup(filename="b.db", path="/x/b.db", dialect="sqlite", kind="full",
                 status="completed", trigger="manual", size_bytes=10, sha256="abc")
    db_session.add(rec)
    await db_session.commit()
    got = (await db_session.execute(select(Backup))).scalars().all()
    assert len(got) == 1 and got[0].sha256 == "abc"
```

(Use the project's existing async DB session fixture. Inspect `tests/conftest.py` for the exact fixture name — it is likely `db_session` or `db`; match whatever `tests/test_*` files already use.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py::test_backup_model_persists -p no:randomly -n0 -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.backup'`

- [ ] **Step 3: Create the model**

Create `app/models/backup.py` (mirror `app/models/report_archive.py` style):

```python
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    dialect: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="full")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("idx_backups_status", "status"),)
```

- [ ] **Step 4: Register model in alembic/env.py**

In `alembic/env.py`, within the `# noqa: F401` import block (~lines 8-21), add a line alongside the others:

```python
import app.models.backup  # noqa: F401
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py::test_backup_model_persists -p no:randomly -n0 -v`
Expected: PASS (tests create tables from metadata; the model is now registered)

- [ ] **Step 6: Create the migration**

Create `alembic/versions/c3d4e5f6a7b8_backups_table.py`:

```python
"""backups table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a8
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("dialect", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("trigger", sa.String(length=20), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("triggered_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_backups_status", "backups", ["status"])
    op.create_index("ix_backups_created_at", "backups", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_backups_created_at", table_name="backups")
    op.drop_index("idx_backups_status", table_name="backups")
    op.drop_table("backups")
```

- [ ] **Step 7: Verify migration applies (dev DB)**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m alembic upgrade head && .venv/Scripts/python.exe -m alembic current`
Expected: output ends with `c3d4e5f6a7b8 (head)`

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/backend/app/models/backup.py scada-reporter/backend/alembic/env.py scada-reporter/backend/alembic/versions/c3d4e5f6a7b8_backups_table.py scada-reporter/backend/tests/test_backup_engine.py
git commit -m "feat(backup): add Backup model and migration"
```

---

### Task 3: BackupEngine — create snapshot (SQLite + Postgres)

**Files:**
- Create: `app/services/backup_engine.py`
- Test: `tests/test_backup_engine.py`

**Interfaces:**
- Consumes: `settings.BACKUP_DIR`, `settings.DATABASE_URL`.
- Produces:
  - `def sqlite_db_path(url: str) -> str | None` — file path from a sqlite URL, else None.
  - `def sha256_file(path: str) -> str`.
  - `async def create_snapshot(*, dest_dir: str, db_url: str, timestamp: str) -> dict` — returns
    `{"filename": str, "path": str, "dialect": str, "size_bytes": int, "sha256": str}`. Raises on failure.
    `timestamp` is caller-supplied (e.g. `"20260627-031500"`) because scripts must not call `datetime.now()` internally for testability.
  - `def verify_snapshot(path: str, dialect: str) -> bool` — SQLite: `PRAGMA integrity_check` == "ok".

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backup_engine.py`:

```python
import os
import sqlite3

from app.services import backup_engine as be


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py -k "snapshot or db_path" -p no:randomly -n0 -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.backup_engine'`

- [ ] **Step 3: Implement the engine**

Create `app/services/backup_engine.py`:

```python
"""Dialect-aware DB snapshot/restore. No FastAPI imports — pure service layer."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3

from app.core.config import settings


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
        "pg_dump", "-Fc", "-d", libpq, "-f", dest_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py -k "snapshot or db_path" -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/backup_engine.py scada-reporter/backend/tests/test_backup_engine.py
git commit -m "feat(backup): dialect-aware snapshot engine with integrity check"
```

---

### Task 4: BackupEngine — restore + retention prune

**Files:**
- Modify: `app/services/backup_engine.py`
- Test: `tests/test_backup_engine.py`

**Interfaces:**
- Consumes: `create_snapshot`, `sqlite_db_path`, `verify_snapshot` (Task 3).
- Produces:
  - `def restore_snapshot(*, backup_path: str, db_url: str) -> None` — SQLite: validates the
    backup, then copies its pages into the live DB file via the sqlite3 online backup API
    (overwrites live contents in place; WAL-safe). Postgres: raises `NotImplementedError`
    (operator runs `pg_restore` out-of-band; see docstring). Raises `FileNotFoundError` if
    `backup_path` missing, `ValueError` if integrity check fails.
  - `def expired_backup_ids(rows: list, *, retention_days: int, now_ts: float) -> list[int]` —
    pure function returning ids older than retention. `rows` items expose `.id` and
    `.created_at` (UTC datetime). `now_ts` is a caller-supplied epoch seconds.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backup_engine.py`:

```python
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace


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
        be.restore_snapshot(backup_path=str(tmp_path / "nope.db"),
                            db_url="sqlite+aiosqlite:///x.db")


def test_expired_backup_ids():
    now = datetime(2026, 6, 27, tzinfo=UTC)
    rows = [
        SimpleNamespace(id=1, created_at=now - timedelta(days=400)),
        SimpleNamespace(id=2, created_at=now - timedelta(days=10)),
    ]
    assert be.expired_backup_ids(rows, retention_days=365, now_ts=now.timestamp()) == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py -k "restore or expired" -p no:randomly -n0 -v`
Expected: FAIL with `AttributeError: module 'app.services.backup_engine' has no attribute 'restore_snapshot'`

- [ ] **Step 3: Implement restore + prune**

Append to `app/services/backup_engine.py`:

```python
from datetime import UTC, datetime


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py -k "restore or expired" -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 5: Run the full engine test file**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py -p no:randomly -n0 -v`
Expected: PASS (all engine tests)

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/backup_engine.py scada-reporter/backend/tests/test_backup_engine.py
git commit -m "feat(backup): restore via sqlite online-backup API + retention prune helper"
```

---

### Task 5: API router — create / list / download / delete

**Files:**
- Create: `app/api/backup.py`
- Modify: `app/main.py` (add `include_router`)
- Test: `tests/test_backup_api.py`

**Interfaces:**
- Consumes: `create_snapshot`, `restore_snapshot`, `expired_backup_ids` (Tasks 3-4); `Backup` model (Task 2); `require_role`, `require_writable` deps.
- Produces (router `prefix="/backup"`, registered under `/api`, so paths are `/api/backup...`):
  - `POST /backup` → `BackupOut` (create on-demand, trigger="manual").
  - `GET /backup` → `list[BackupOut]` (newest first).
  - `GET /backup/{id}/download` → `FileResponse`.
  - `DELETE /backup/{id}` → `{"deleted": id}` (removes row + file).
  - `BackupOut` schema: `id, filename, dialect, kind, status, trigger, size_bytes, sha256, error, created_at, completed_at`.

Determine the exact DB-session dependency and the current-user dependency by reading `app/api/reports.py` imports (e.g. `from app.core.database import get_db` or similar, and `from app.api.auth import require_role`). Use those exact symbols below — replace `get_db` if the project name differs.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backup_api.py`. Mirror auth setup from an existing API test (e.g. `tests/test_reports*` or `tests/test_dashboard*`) — reuse its admin-auth header fixture/helper. Skeleton:

```python
import pytest


@pytest.mark.asyncio
async def test_create_and_list_backup(client, admin_headers, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    r = await client.post("/api/backup", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "verified"
    assert body["sha256"]
    lst = await client.get("/api/backup", headers=admin_headers)
    assert lst.status_code == 200 and len(lst.json()) == 1


@pytest.mark.asyncio
async def test_create_backup_requires_admin(client, operator_headers):
    r = await client.post("/api/backup", headers=operator_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_backup(client, admin_headers, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    created = (await client.post("/api/backup", headers=admin_headers)).json()
    d = await client.delete(f"/api/backup/{created['id']}", headers=admin_headers)
    assert d.status_code == 200 and d.json()["deleted"] == created["id"]
    lst = await client.get("/api/backup", headers=admin_headers)
    assert lst.json() == []
```

Match `client`, `admin_headers`, `operator_headers` to the actual fixtures/helpers in `tests/conftest.py`. If the suite builds auth headers via a helper instead of fixtures, call that helper.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -p no:randomly -n0 -v`
Expected: FAIL (404 on `/api/backup` — router not registered)

- [ ] **Step 3: Implement the router**

Create `app/api/backup.py` (adapt `get_db`/session dep name to match `app/api/reports.py`):

```python
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.api.license_guard import require_writable
from app.core.config import settings
from app.core.database import get_db  # adjust if the project's session dep differs
from app.models.backup import Backup
from app.services import backup_engine as be

router = APIRouter(prefix="/backup", tags=["backup"])


class BackupOut(BaseModel):
    id: int
    filename: str
    dialect: str
    kind: str
    status: str
    trigger: str
    size_bytes: int | None
    sha256: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


def _ts(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S")


async def run_backup(db: AsyncSession, *, trigger: str, user_id: int | None) -> Backup:
    """Create a snapshot, persist metadata. Shared by API + scheduler."""
    now = datetime.now(UTC)
    rec = Backup(filename="", path="", dialect="", kind="full",
                 status="running", trigger=trigger, triggered_by=user_id,
                 created_at=now)
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    try:
        res = await be.create_snapshot(
            dest_dir=settings.BACKUP_DIR, db_url=settings.DATABASE_URL, timestamp=_ts(now)
        )
        rec.filename = res["filename"]
        rec.path = res["path"]
        rec.dialect = res["dialect"]
        rec.size_bytes = res["size_bytes"]
        rec.sha256 = res["sha256"]
        rec.status = "verified"
        rec.completed_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001 — record failure, surface to caller
        rec.status = "failed"
        rec.error = str(exc)[:512]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Backup failed: {rec.error}") from exc
    await db.commit()
    await db.refresh(rec)
    return rec


@router.post("", response_model=BackupOut)
async def create_backup(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> Backup:
    return await run_backup(db, trigger="manual", user_id=getattr(user, "id", None))


@router.get("", response_model=list[BackupOut])
async def list_backups(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
) -> list[Backup]:
    rows = (
        await db.execute(select(Backup).order_by(Backup.created_at.desc()))
    ).scalars().all()
    return list(rows)


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
) -> FileResponse:
    rec = await db.get(Backup, backup_id)
    if rec is None or not rec.path or not os.path.exists(rec.path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(rec.path, filename=rec.filename, media_type="application/octet-stream")


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    rec = await db.get(Backup, backup_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.path and os.path.exists(rec.path):
        os.remove(rec.path)
    await db.delete(rec)
    await db.commit()
    return {"deleted": backup_id}
```

- [ ] **Step 4: Register the router**

In `app/main.py`, alongside the other `include_router` calls (~lines 187-209), add the import with its siblings and:

```python
app.include_router(backup.router, prefix="/api")
```

(Add `backup` to the existing `from app.api import (...)` import group.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/backup.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_backup_api.py
git commit -m "feat(backup): create/list/download/delete API, admin+writable gated"
```

---

### Task 6: API router — restore endpoint

**Files:**
- Modify: `app/api/backup.py`
- Test: `tests/test_backup_api.py`

**Interfaces:**
- Consumes: `restore_snapshot` (Task 4), `Backup`, `run_backup` (Task 5).
- Produces: `POST /backup/{id}/restore` body `{"confirm": "RESTORE"}` → `{"restored": id}`.
  Admin + writable gated. Returns 400 unless `confirm == "RESTORE"` (guard against accidental
  destructive calls). Takes a safety snapshot of the current DB before overwriting.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backup_api.py`:

```python
@pytest.mark.asyncio
async def test_restore_requires_confirm(client, admin_headers, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    created = (await client.post("/api/backup", headers=admin_headers)).json()
    bad = await client.post(f"/api/backup/{created['id']}/restore",
                            json={"confirm": "nope"}, headers=admin_headers)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_restore_requires_admin(client, operator_headers):
    r = await client.post("/api/backup/1/restore",
                          json={"confirm": "RESTORE"}, headers=operator_headers)
    assert r.status_code == 403
```

(A full happy-path restore over the shared in-memory test engine is out of scope for the API
test — the engine-level restore is already covered in Task 4. These tests lock the gating +
confirmation contract.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -k restore -p no:randomly -n0 -v`
Expected: FAIL (404 — restore route missing)

- [ ] **Step 3: Implement the restore endpoint**

Append to `app/api/backup.py` (add `import asyncio` at top if not present):

```python
class RestoreRequest(BaseModel):
    confirm: str


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    body: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    if body.confirm != "RESTORE":
        raise HTTPException(status_code=400, detail="Confirmation token must be 'RESTORE'")
    rec = await db.get(Backup, backup_id)
    if rec is None or not rec.path or not os.path.exists(rec.path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    # safety snapshot of the CURRENT state before overwriting
    await run_backup(db, trigger="manual", user_id=getattr(user, "id", None))
    try:
        await asyncio.to_thread(
            be.restore_snapshot, backup_path=rec.path, db_url=settings.DATABASE_URL
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"restored": backup_id}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -k restore -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/backup.py scada-reporter/backend/tests/test_backup_api.py
git commit -m "feat(backup): restore endpoint with confirmation token + pre-restore safety snapshot"
```

---

### Task 7: Scheduled nightly backup + retention prune

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/test_backup_api.py` (job-registration assertion)

**Interfaces:**
- Consumes: `run_backup` (Task 5), `expired_backup_ids` (Task 4), `settings.BACKUP_SCHEDULE_CRON`, `settings.BACKUP_RETENTION_DAYS`, `settings.RUN_BACKUP_SCHEDULER`.
- Produces: `async def scheduled_backup_job()` registered with id `"db_backup"` on the cron from `BACKUP_SCHEDULE_CRON`; runs a backup then prunes expired rows+files. Registered inside `start_scheduler()` next to the existing `plc_incident_prune` job.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backup_api.py`:

```python
@pytest.mark.asyncio
async def test_scheduled_backup_runs(tmp_path, monkeypatch, db_session):
    from app.core.config import settings
    from app.services.scheduler import scheduled_backup_job
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    await scheduled_backup_job()  # must not raise; creates a verified backup row
    from sqlalchemy import select
    from app.models.backup import Backup
    rows = (await db_session.execute(select(Backup))).scalars().all()
    assert any(r.trigger == "scheduled" and r.status == "verified" for r in rows)
```

Note: `scheduled_backup_job` must open its OWN session (it runs outside a request). Use the project's session factory (`AsyncSessionLocal` from `app/core/database.py`). The test reads via `db_session` which shares the same in-memory engine.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -k scheduled -p no:randomly -n0 -v`
Expected: FAIL with `ImportError: cannot import name 'scheduled_backup_job'`

- [ ] **Step 3: Implement the job**

In `app/services/scheduler.py`, add imports near the top:

```python
import os
from datetime import UTC, datetime

from sqlalchemy import select
```

Add the job function (module level):

```python
async def scheduled_backup_job() -> None:
    """Nightly backup + retention prune. Opens its own session."""
    from app.api.backup import run_backup  # local import avoids router import cycle
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.models.backup import Backup
    from app.services import backup_engine as be

    async with AsyncSessionLocal() as db:
        await run_backup(db, trigger="scheduled", user_id=None)
        rows = (await db.execute(select(Backup))).scalars().all()
        now_ts = datetime.now(UTC).timestamp()
        for bid in be.expired_backup_ids(
            rows, retention_days=settings.BACKUP_RETENTION_DAYS, now_ts=now_ts
        ):
            rec = await db.get(Backup, bid)
            if rec is None:
                continue
            if rec.path and os.path.exists(rec.path):
                os.remove(rec.path)
            await db.delete(rec)
        await db.commit()
```

In `start_scheduler()`, after the existing `plc_incident_prune` `add_job` block, register the backup job (parse the 5-field cron):

```python
    if settings.RUN_BACKUP_SCHEDULER:
        m, h, dom, mon, dow = settings.BACKUP_SCHEDULE_CRON.split()
        _scheduler.add_job(
            scheduled_backup_job,
            "cron",
            id="db_backup",
            minute=m, hour=h, day=dom, month=mon, day_of_week=dow,
            replace_existing=True,
        )
```

(Reference the module-level scheduler the same way `plc_incident_prune` is registered — match the existing `_scheduler` variable name in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_api.py -k scheduled -p no:randomly -n0 -v`
Expected: PASS

- [ ] **Step 5: Run the full backend backup test files**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_backup_engine.py tests/test_backup_api.py -p no:randomly -n0 -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/scheduler.py scada-reporter/backend/tests/test_backup_api.py
git commit -m "feat(backup): nightly scheduled backup + retention prune"
```

---

### Task 8: Frontend — API client functions

**Files:**
- Modify: `frontend/src/api/client.ts`
- Test: manual (TS compiles via `pnpm tsc` / build)

**Interfaces:**
- Produces (mirror existing `getRuntimeStatus`/`startCollector` style in `client.ts`):
  - `listBackups()` → `api.get<BackupItem[]>('/backup')`
  - `createBackup()` → `api.post<BackupItem>('/backup')`
  - `deleteBackup(id)` → `api.delete<{deleted:number}>(`/backup/${id}`)`
  - `restoreBackup(id)` → `api.post<{restored:number}>(`/backup/${id}/restore`, {confirm:'RESTORE'})`
  - `backupDownloadUrl(id)` → string (`/backup/${id}/download`, prefixed like other absolute API URLs)
  - `BackupItem` TS interface matching `BackupOut`.

- [ ] **Step 1: Add types + functions**

In `frontend/src/api/client.ts`, add:

```typescript
export interface BackupItem {
  id: number
  filename: string
  dialect: string
  kind: string
  status: string
  trigger: string
  size_bytes: number | null
  sha256: string | null
  error: string | null
  created_at: string
  completed_at: string | null
}

export const listBackups = () => api.get<BackupItem[]>('/backup')
export const createBackup = () => api.post<BackupItem>('/backup')
export const deleteBackup = (id: number) => api.delete<{ deleted: number }>(`/backup/${id}`)
export const restoreBackup = (id: number) =>
  api.post<{ restored: number }>(`/backup/${id}/restore`, { confirm: 'RESTORE' })
export const backupDownloadUrl = (id: number) => `${api.defaults.baseURL}/backup/${id}/download`
```

(Match the actual axios instance name and base-URL accessor used in this file — inspect the top of `client.ts`. If downloads need the auth token as a query param or a blob fetch, follow whatever existing file-download helper the reports feature uses instead of a bare URL.)

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd scada-reporter/frontend && pnpm tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts
git commit -m "feat(backup): frontend API client functions"
```

---

### Task 9: Frontend — SettingsBackupCard + mount

**Files:**
- Create: `frontend/src/pages/SettingsBackupCard.tsx`
- Modify: `frontend/src/pages/Settings.tsx` (mount card, admin-only)
- Modify: i18n string files (add labels)

**Interfaces:**
- Consumes: `listBackups`, `createBackup`, `deleteBackup`, `restoreBackup`, `backupDownloadUrl`, `BackupItem` (Task 8).
- Produces: `SettingsBackupCard` default export — admin-only card listing backups (filename, age, size, status), a "Yedek Al" button, per-row download/delete, and a guarded restore (`window.confirm`). Shows newest-first list + last-backup line.

- [ ] **Step 1: Create the card**

Create `frontend/src/pages/SettingsBackupCard.tsx` (mirror state/handler/`cardCls` pattern from `SettingsRuntimeCard.tsx`):

```tsx
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listBackups, createBackup, deleteBackup, restoreBackup, backupDownloadUrl,
  type BackupItem,
} from '../api/client'

const cardCls = 'bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 space-y-4'

function fmtSize(n: number | null): string {
  if (!n) return '—'
  const mb = n / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`
}

export default function SettingsBackupCard() {
  const { t } = useTranslation()
  const [items, setItems] = useState<BackupItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    try {
      const res = await listBackups()
      setItems(res.data)
    } catch {
      setError(t('backup_load_failed'))
    }
  }

  useEffect(() => { void refresh() }, [])

  async function onCreate() {
    setBusy(true); setError(null)
    try { await createBackup(); await refresh() }
    catch { setError(t('backup_create_failed')) }
    finally { setBusy(false) }
  }

  async function onDelete(id: number) {
    if (!window.confirm(t('backup_confirm_delete'))) return
    setBusy(true)
    try { await deleteBackup(id); await refresh() }
    catch { setError(t('backup_delete_failed')) }
    finally { setBusy(false) }
  }

  async function onRestore(id: number) {
    if (!window.confirm(t('backup_confirm_restore'))) return
    setBusy(true); setError(null)
    try { await restoreBackup(id); await refresh() }
    catch { setError(t('backup_restore_failed')) }
    finally { setBusy(false) }
  }

  return (
    <div className={cardCls}>
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase">{t('backup_title')}</h2>
        <p className="text-xs text-gray-500 mt-1">{t('backup_hint')}</p>
      </div>

      <button
        onClick={onCreate}
        disabled={busy}
        className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm disabled:opacity-50"
      >
        {t('backup_create')}
      </button>

      {items.length === 0 && <p className="text-xs text-gray-500">{t('backup_none')}</p>}

      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.id} className="flex items-center justify-between text-sm border-b border-gray-800 pb-2">
            <div className="min-w-0">
              <p className="truncate text-gray-200">{b.filename}</p>
              <p className="text-xs text-gray-500">
                {new Date(b.created_at).toLocaleString()} · {fmtSize(b.size_bytes)} · {b.status}
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <a href={backupDownloadUrl(b.id)} className="text-xs text-blue-400 hover:underline">
                {t('backup_download')}
              </a>
              <button onClick={() => onRestore(b.id)} disabled={busy}
                className="text-xs text-amber-400 hover:underline disabled:opacity-50">
                {t('backup_restore')}
              </button>
              <button onClick={() => onDelete(b.id)} disabled={busy}
                className="text-xs text-red-400 hover:underline disabled:opacity-50">
                {t('backup_delete')}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Mount it in Settings (admin-only)**

In `frontend/src/pages/Settings.tsx`, import and render alongside `SettingsRuntimeCard`, gated the same way:

```tsx
import SettingsBackupCard from './SettingsBackupCard'
// ...
{user?.role === 'admin' && <SettingsBackupCard />}
```

- [ ] **Step 3: Add i18n strings**

Add these keys to each language file (at minimum `tr` and `en`; follow the project's i18n file layout). Turkish values:

```
backup_title: "Yedekleme"
backup_hint: "Veritabanı yedeklerini al, indir, geri yükle"
backup_create: "Yedek Al"
backup_none: "Henüz yedek yok"
backup_download: "İndir"
backup_restore: "Geri Yükle"
backup_delete: "Sil"
backup_confirm_delete: "Bu yedeği silmek istediğinize emin misiniz?"
backup_confirm_restore: "DİKKAT: Mevcut veritabanının üzerine yazılacak. Önce güvenlik yedeği alınır. Devam edilsin mi?"
backup_load_failed: "Yedekler yüklenemedi"
backup_create_failed: "Yedek alınamadı"
backup_delete_failed: "Yedek silinemedi"
backup_restore_failed: "Geri yükleme başarısız"
```

(Provide English equivalents in the `en` file. If the project ships ru/de/ar, add keys there too or they will fall back to the key string.)

- [ ] **Step 4: Verify build**

Run: `cd scada-reporter/frontend && pnpm tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/SettingsBackupCard.tsx scada-reporter/frontend/src/pages/Settings.tsx scada-reporter/frontend/src/i18n
git commit -m "feat(backup): Settings backup card (admin) with create/download/restore/delete"
```

---

### Task 10: Full-suite verification + docs

**Files:**
- Create: `docs/backup-restore.md`
- Test: full backend suite

- [ ] **Step 1: Run full backend suite**

Run: `cd scada-reporter/backend && just test`
Expected: all tests pass (existing 247+ plus the new backup tests). If any unrelated test now fails, investigate before proceeding — do not claim success.

- [ ] **Step 2: Lint + types**

Run: `cd scada-reporter/backend && just lint && just typecheck`
Expected: clean (ruff + mypy)

- [ ] **Step 3: Write the ops doc**

Create `docs/backup-restore.md` covering: what gets backed up (full DB snapshot), where files land (`BACKUP_DIR`), schedule (`BACKUP_SCHEDULE_CRON`), retention (`BACKUP_RETENTION_DAYS`), how SQLite restore works (online backup API, stop collector first), and the **Postgres restore** runbook: `pg_restore --clean --if-exists -d "$DATABASE_URL" backup-YYYYMMDD-HHMMSS.dump`. State explicitly that physical PITR (pgBackRest/WAL-G) is the recommended prod path and is tracked in a separate plan.

- [ ] **Step 4: Commit**

```bash
git add scada-reporter/backend/docs/backup-restore.md
git commit -m "docs(backup): backup/restore operations guide"
```

---

## Self-Review Notes

- **Spec coverage:** scheduled + on-demand backup (Tasks 5, 7) ✓; integrity verify (Task 3 `verify_snapshot`, status `verified`) ✓; checksum (sha256, Task 3) ✓; retention (Tasks 4, 7) ✓; restore + safety snapshot + confirmation (Task 6) ✓; admin + demo gating (Tasks 5, 6) ✓; UI list/create/download/restore/delete (Task 9) ✓; dialect-aware SQLite + Postgres (Task 3) ✓. Prod PITR explicitly deferred to a separate plan (Global Constraints + Task 10 doc).
- **Type consistency:** `run_backup(db, *, trigger, user_id)` defined Task 5, reused Tasks 6-7 identically. `create_snapshot(*, dest_dir, db_url, timestamp)` Task 3, called Task 5. `expired_backup_ids(rows, *, retention_days, now_ts)` Task 4, called Task 7. `BackupOut`/`BackupItem` fields match the `Backup` model columns (Task 2).
- **Adapt-to-codebase flags (resolve while implementing, do not skip):** the DB-session dependency symbol (`get_db` vs project name), the test auth fixtures (`client`/`admin_headers`/`operator_headers` vs helpers), the `app.api` import group in `main.py`, the `_scheduler` variable name in `scheduler.py`, the axios instance + download helper in `client.ts`, and the i18n file layout. Each task names the file to read for the exact pattern.
