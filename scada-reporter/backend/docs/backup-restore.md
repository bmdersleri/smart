# Application Database Backup & Restore

**Feature:** Application-managed DB snapshot/restore — scheduled nightly + on-demand, integrity-verified, admin-controlled.
**Scope:** SQLite (development) and PostgreSQL/TimescaleDB (production) logical snapshots only.
**Physical PITR** (pgBackRest/WAL-G continuous archiving) is the recommended production path for point-in-time recovery and is tracked in a separate infrastructure plan — out of scope here.

---

## What Gets Backed Up

Each backup is a **single consistent snapshot of the entire database**:

| Dialect | File format | Mechanism |
|---------|-------------|-----------|
| SQLite (dev) | `.db` file | `VACUUM INTO` — WAL-safe, defragmented, page-level copy |
| PostgreSQL/TimescaleDB (prod) | `.dump` file | `pg_dump -Fc` — compressed custom format |

After every snapshot the engine runs an integrity check (`PRAGMA integrity_check` for SQLite; file-size/existence check for Postgres dumps) and computes a SHA-256 checksum. The backup record carries `status: verified` only if both pass; otherwise `status: failed` and the error is recorded.

**Not included:** generated report files on disk (back up `REPORT_ARCHIVE` files separately), `.env` secrets, or Grafana volume state — see `docs/backup-recovery.md` for the full disaster-recovery runbook.

---

## Where Files Land

Backup files are written to the directory configured by `BACKUP_DIR` (default: `backups/`, relative to the backend working directory). Each file is named:

```
backup-YYYYMMDD-HHMMSS.db    # SQLite
backup-YYYYMMDD-HHMMSS.dump  # Postgres
```

The absolute path is recorded in the `backups` table for download and restore.

---

## Configuration

All knobs live in `app/core/config.py` and are overridable via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_DIR` | `"backups"` | Directory where snapshot files are written |
| `BACKUP_RETENTION_DAYS` | `365` | Backups older than this are auto-pruned by the nightly job |
| `BACKUP_SCHEDULE_CRON` | `"0 3 * * *"` | 5-field cron for the nightly backup (default: daily 03:00 UTC) |
| `RUN_BACKUP_SCHEDULER` | `True` | Set to `False` to disable the scheduled backup entirely (on-demand via API still works) |

---

## Schedule & Retention

The APScheduler cron job `db_backup` runs at the time configured by `BACKUP_SCHEDULE_CRON`. On each run it:

1. Creates a full snapshot via `run_backup(trigger="scheduled")`.
2. Queries all backup records.
3. Deletes any records (and their files) whose `created_at` is older than `BACKUP_RETENTION_DAYS`.

The job is registered during `start_scheduler()` in `app/services/scheduler.py` only when `RUN_BACKUP_SCHEDULER` is `True`. You can verify the job is registered via the scheduler state or by inspecting the APScheduler job store.

---

## API Reference

All endpoints are **admin-only**. All mutating endpoints (`POST`, `DELETE`) are also blocked in **demo mode** (require the instance to be `writable`).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/backup` | Trigger an on-demand backup immediately |
| `GET` | `/api/backup` | List all backup records (newest first) |
| `GET` | `/api/backup/{id}/download` | Download the backup file as `application/octet-stream` |
| `POST` | `/api/backup/{id}/restore` | Restore from this backup (see restore runbook below) |
| `DELETE` | `/api/backup/{id}` | Delete the backup record and its file |

### Create backup

```http
POST /api/backup
Authorization: Bearer <admin-token>
```

Response (HTTP 200):

```json
{
  "id": 42,
  "filename": "backup-20260628-030000.db",
  "dialect": "sqlite",
  "kind": "full",
  "status": "verified",
  "trigger": "manual",
  "size_bytes": 4194304,
  "sha256": "a1b2c3...",
  "error": null,
  "created_at": "2026-06-28T03:00:00Z",
  "completed_at": "2026-06-28T03:00:02Z"
}
```

### Restore

```http
POST /api/backup/{id}/restore
Authorization: Bearer <admin-token>
Content-Type: application/json

{"confirm": "RESTORE"}
```

The body must contain `{"confirm": "RESTORE"}` exactly — this is the safety confirmation token. Omitting it or sending any other value returns HTTP 400.

Before overwriting the live database, the endpoint automatically **takes a safety snapshot** of the current state (`trigger: "manual"`) so you can undo the restore if needed.

---

## UI

The backup card is available in the **Settings** page (admin users only). It shows:

- List of all backups with status, size, timestamp, and SHA-256.
- "New Backup" button to trigger an on-demand snapshot.
- Download link for each backup file.
- Restore button (with confirmation prompt).
- Delete button.

---

## SQLite Restore Runbook (Development)

> **Stop the collector and scheduler first** before restoring in development. The SQLite online backup API copies pages into the live file; concurrent writes from the collector or scheduler can corrupt the restore. Use `just restart-backend` to stop the backend cleanly before restoring, or ensure the backend is not running.

The API endpoint (`POST /api/backup/{id}/restore`) performs the restore automatically:

1. Validates `{"confirm": "RESTORE"}` in the request body.
2. Takes a safety snapshot of the current database.
3. Calls `restore_snapshot(backup_path, db_url)` via `asyncio.to_thread`.
4. `restore_snapshot` uses the **sqlite3 online backup API** (`sqlite3.Connection.backup()`) to copy pages from the backup file into the live database file.

**Manual restore (outside the API):**

```python
import sqlite3

src = sqlite3.connect("backups/backup-YYYYMMDD-HHMMSS.db")
dst = sqlite3.connect("scada_reporter.db")
src.backup(dst)
dst.commit()
dst.close()
src.close()
```

Or using the SQLite CLI (requires WAL checkpoint afterward):

```bash
sqlite3 scada_reporter.db ".restore backups/backup-YYYYMMDD-HHMMSS.db"
sqlite3 scada_reporter.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

---

## PostgreSQL Restore Runbook (Production)

> **The API endpoint does not automate Postgres restore** (`restore_snapshot` raises `NotImplementedError` for Postgres). Use the out-of-band procedure below.

Download the dump file via the API or directly from `BACKUP_DIR`, then restore with `pg_restore`:

```bash
# Restore into the existing database (drops and recreates all objects first)
pg_restore \
  --clean \
  --if-exists \
  -d "$DATABASE_URL" \
  backup-YYYYMMDD-HHMMSS.dump
```

**Full procedure:**

```bash
# 1. Stop the application backend (prevent new writes)
# 2. Download the dump from Settings → Backup or copy from BACKUP_DIR

# 3. Restore (replace $DATABASE_URL with the libpq URL, e.g. postgresql://scada:pass@host:5432/scada_reporter)
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -d "postgresql://scada:scada123@localhost:5432/scada_reporter" \
  backup-YYYYMMDD-HHMMSS.dump

# 4. Run Alembic to ensure the schema is at head (the dump may be from an older migration)
cd scada-reporter/backend
.venv/Scripts/python.exe -m alembic upgrade head

# 5. Restart the backend
just restart-backend
```

**TimescaleDB note:** For a logical `pg_dump`/`pg_restore` round-trip the `timescaledb_pre_restore()` / `timescaledb_post_restore()` calls are **not required**. They are only needed for binary (file-system level) restores.

---

## Production PITR Recommendation

For production systems where data loss must be minimized to seconds rather than hours, use a **physical PITR solution** such as pgBackRest or WAL-G alongside (or instead of) these application-level snapshots:

- **pgBackRest**: full/incremental/differential backups + WAL archiving, streaming restore, parallel compression.
- **WAL-G**: WAL archiving to S3/GCS/Azure, point-in-time restore to any committed transaction.

Physical PITR is the recommended production path and is tracked in a separate infrastructure plan. The application-level snapshots documented here serve as a complementary, admin-accessible quick backup mechanism.
