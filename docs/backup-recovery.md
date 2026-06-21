# Backup / Restore / Disaster Recovery Runbook

**System:** EKONT SMART REPORT — Water/wastewater plant SCADA data acquisition and reporting
**Database:** TimescaleDB (PostgreSQL) in production, SQLite in development
**Last verified against:** `app/core/config.py`, `app/core/timescaledb.py`, `app/models/report_archive.py`, `docker/docker-compose.yml`

---

## Table of Contents

1. [Data Inventory](#1-data-inventory)
2. [Backup Procedures](#2-backup-procedures)
3. [Restore Runbook](#3-restore-runbook)
4. [Retention and Rollup Policy](#4-retention-and-rollup-policy)

---

## 1. Data Inventory

### 1.1 Production (PostgreSQL / TimescaleDB)

| Asset | Location | Notes |
|---|---|---|
| TimescaleDB data | Docker volume `pgdata` → `/var/lib/postgresql/data` | Primary store — all tag readings, CAGGs, users, reports |
| Report archive metadata | `report_archive` table (rows in DB) | status, file_path, created_at, tag_ids, etc. |
| Report archive result | `report_archive.result_json` column | gzip-compressed summary — stored **in the DB** as `LargeBinary` |
| Generated report files | Filesystem path recorded in `report_archive.file_path` (up to 512 chars) | Excel / PDF files on the application server disk |
| Environment config | `.env` file — **gitignored** | Must be backed up out-of-band (see §2.4) |
| Schema migrations | `scada-reporter/backend/alembic/` — tracked in Git | No separate backup needed; restore from Git |
| Grafana provisioning | `docker/grafana/datasources/` and `docker/grafana/dashboards/` — tracked in Git | Datasource and dashboard JSON definitions |
| Grafana runtime state | Docker volume `grafana-data` → `/var/lib/grafana` | User accounts, manual dashboards, saved preferences — **not in Git** |
| Portainer state | Docker volume `portainer-data` → `/data` | Container management state — restore is optional |

### 1.2 Development (SQLite)

| Asset | Location | Notes |
|---|---|---|
| SQLite database | `scada-reporter/backend/scada_reporter.db` | All tables in one file |
| WAL / SHM files | `scada_reporter.db-wal`, `scada_reporter.db-shm` | Checkpoint before copying (see §2.5) |
| Generated report files | Same as production — `file_path` in `report_archive` table | |
| Environment config | `.env` file — **gitignored** | Back up manually |

> **SQLite vs PostgreSQL:** The application selects the database driver based on the `DATABASE_URL` setting. Default value is `postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter`. In `.env.production.example`, `AUTO_CREATE_TABLES=False` is set — production schema is managed exclusively by Alembic migrations.

---

## 2. Backup Procedures

### 2.1 PostgreSQL / TimescaleDB — Logical Backup (`pg_dump`)

A logical dump via `pg_dump` is the recommended path for most backup/restore scenarios. It produces a portable SQL file that works across minor TimescaleDB versions.

```bash
# Minimal logical dump (schema + data)
pg_dump \
  --host=localhost \
  --port=5432 \
  --username=scada \
  --dbname=scada_reporter \
  --no-owner \
  --no-privileges \
  --format=custom \
  --file="/backup/scada_reporter_$(date +%Y%m%d_%H%M%S).dump"
```

**Flags explained:**
- `--no-owner` / `--no-privileges` — omit ownership and grant statements so the dump can be restored to any PostgreSQL role
- `--format=custom` — compressed, parallel-restorable format (preferred over plain SQL)

**TimescaleDB-specific note:** For a *binary* (file-system level) restore of TimescaleDB you must call `timescaledb_pre_restore()` before `pg_restore` and `timescaledb_post_restore()` after. For the logical `pg_dump` / `pg_restore` path used here, these calls are **not required** — the logical dump is the simpler and recommended approach.

**Scheduling (cron example):**
```cron
0 2 * * * pg_dump --host=localhost --port=5432 --username=scada --dbname=scada_reporter --no-owner --no-privileges --format=custom --file="/backup/scada_reporter_$(date +\%Y\%m\%d_\%H\%M\%S).dump"
```

### 2.2 Docker Named-Volume Backup

Back up the raw volume data to capture any state that `pg_dump` may miss (tablespace files, custom extensions). This is a complementary snapshot, not a replacement for the logical dump.

```bash
# Stop the container first to ensure a consistent snapshot
docker stop smart-db-1

# Compress the volume into a tar archive
docker run --rm \
  -v pgdata:/data \
  -v /backup:/backup \
  alpine \
  tar czf /backup/pgdata_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart the container
docker start smart-db-1
```

Repeat the same pattern for the Grafana volume:

```bash
docker stop smart-grafana-1

docker run --rm \
  -v grafana-data:/data \
  -v /backup:/backup \
  alpine \
  tar czf /backup/grafana_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

docker start smart-grafana-1
```

> **Volume names** are defined in `docker/docker-compose.yml`: `pgdata`, `grafana-data`, `portainer-data`. Verify actual container names with `docker ps`.

### 2.3 Report Archive Files

Generated Excel/PDF files are stored on the application server at the path recorded in `report_archive.file_path` (up to 512 characters per row). The DB row also contains `result_json` (gzip-compressed summary as `LargeBinary`) which is captured by `pg_dump`. The generated files on disk must be backed up separately:

```bash
# Example: rsync report files to a backup destination
rsync -a --checksum /app/reports/ /backup/reports/
```

Retention of generated files is controlled by `REPORT_ARCHIVE_KEEP_DAYS=365` (see §4).

### 2.4 Environment Configuration (`.env`)

The `.env` file is **gitignored** and contains production secrets (`SECRET_KEY`, database credentials, SMTP passwords). It must be backed up out-of-band:

```bash
# Example: copy to a secrets manager or encrypted backup location
cp /app/.env /backup/secrets/.env_$(date +%Y%m%d)
# Restrict permissions immediately
chmod 600 /backup/secrets/.env_$(date +%Y%m%d)
```

> Use a secrets manager (Vault, AWS Secrets Manager, etc.) or encrypted storage — never commit `.env` to Git. Reference template: `scada-reporter/backend/.env.production.example`.

### 2.5 SQLite Development Backup

SQLite has a Write-Ahead Log (WAL) that must be checkpointed before a safe copy:

```bash
# Checkpoint the WAL so all changes land in the main .db file
sqlite3 scada-reporter/backend/scada_reporter.db "PRAGMA wal_checkpoint(FULL);"

# Now copy the single file
cp scada-reporter/backend/scada_reporter.db /backup/scada_reporter_$(date +%Y%m%d_%H%M%S).db
```

---

## 3. Restore Runbook

Follow these steps in order. Do not skip the Alembic verification step — in production `AUTO_CREATE_TABLES=False`, so the schema comes entirely from migrations.

### Step 1 — Provision a fresh PostgreSQL instance

```bash
# Start the database container
cd docker
docker compose up -d db

# Wait for the health check to pass
docker compose ps db   # state should be "healthy"
```

Default credentials (override via `docker/.env`):
- User: `scada`
- Database: `scada_reporter`
- Port: `5432`

### Step 2 — Restore the logical dump

```bash
pg_restore \
  --host=localhost \
  --port=5432 \
  --username=scada \
  --dbname=scada_reporter \
  --no-owner \
  --no-privileges \
  /backup/scada_reporter_<TIMESTAMP>.dump
```

If restoring a plain SQL dump:

```bash
psql --host=localhost --port=5432 --username=scada --dbname=scada_reporter \
  -f /backup/scada_reporter_<TIMESTAMP>.sql
```

### Step 3 — Verify / advance schema with Alembic

After restoring the dump, confirm Alembic is at the current head (the dump may have been taken from an older schema version):

```bash
cd scada-reporter/backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# Check current revision
alembic current

# Apply any pending migrations
alembic upgrade head

# Confirm
alembic current
```

Expected output: the latest revision hash with `(head)` suffix.

### Step 4 — Restore Grafana provisioning

Grafana datasource and dashboard provisioning configs are in Git — no restore action required; they mount automatically:

```
docker/grafana/datasources/  → /etc/grafana/provisioning/datasources (read-only)
docker/grafana/dashboards/   → /etc/grafana/provisioning/dashboards  (read-only)
```

To restore the `grafana-data` volume (manual dashboards, user accounts):

```bash
docker stop smart-grafana-1

docker run --rm \
  -v grafana-data:/data \
  -v /backup:/backup \
  alpine \
  sh -c "cd /data && tar xzf /backup/grafana_data_<TIMESTAMP>.tar.gz"

docker start smart-grafana-1
```

### Step 5 — Restore report archive files

```bash
rsync -a /backup/reports/ /app/reports/
```

Ensure the paths match what is stored in `report_archive.file_path` rows in the database.

### Step 6 — Restore `.env`

```bash
cp /backup/secrets/.env_<DATE> /app/.env
chmod 600 /app/.env
```

Verify the required production settings are correct:
- `ENVIRONMENT=production`
- `AUTO_CREATE_TABLES=False`
- `DATABASE_URL` pointing to the new DB host
- `SECRET_KEY` set to a strong random value

### Step 7 — Start the application

```bash
# From the project root
just dev
# or in production: start the backend and frontend via your process manager
```

### Step 8 — Verify with readiness probe

```bash
curl -s http://localhost:8001/ready | python -m json.tool
```

Expected response (HTTP 200):

```json
{
  "status": "ready",
  "checks": {
    "db": true,
    "alembic_head": true,
    "scheduler": true
  }
}
```

If any check returns `false`, inspect logs before allowing traffic.

---

## 4. Retention and Rollup Policy

All values in this section are sourced from `app/core/config.py` and `app/core/timescaledb.py`.

### 4.1 Raw Tag Readings — `tag_readings` Hypertable

| Policy | Value | Source |
|---|---|---|
| Compression | Data older than **7 days** is compressed in-place | `add_compression_policy('tag_readings', INTERVAL '7 days')` |
| Retention | Data older than **`RAW_RETENTION_DAYS`** days is dropped | `add_retention_policy('tag_readings', INTERVAL '90 days')` |
| Default `RAW_RETENTION_DAYS` | **90** | `config.py` line `RAW_RETENTION_DAYS: int = 90` |

Override the retention window by setting `RAW_RETENTION_DAYS` in `.env` before the backend starts. The policy is applied at startup via `init_timescaledb()`.

### 4.2 Continuous Aggregates (CAGGs)

Three materialized views are created by `init_continuous_aggregates()`:

| View | Bucket | Refresh start offset | Refresh end offset | Schedule interval |
|---|---|---|---|---|
| `tag_readings_1m` | 1 minute | 3 hours | 1 minute | 1 minute |
| `tag_readings_5m` | 5 minutes | 1 day | 5 minutes | 5 minutes |
| `tag_readings_1h` | 1 hour | 7 days | 1 hour | 30 minutes |

All three CAGGs aggregate `avg`, `min`, `max`, and `count` per `tag_id` and time bucket. They have **no retention policy** (stored indefinitely alongside the hypertable they are derived from; only raw `tag_readings` has the 90-day drop policy).

These views are backed up automatically with `pg_dump` as materialized views.

### 4.3 Daily Rollup — `tag_readings_1d`

| Property | Value |
|---|---|
| View name | `tag_readings_1d` |
| Bucket | 1 day |
| Columns | `avg`, `min`, `max`, `sum`, `n` (count), `first_v`, `last_v` |
| Retention policy | **None** — kept indefinitely |
| Refresh start offset | 7 days |
| Refresh end offset | 1 hour |
| Schedule interval | 1 hour |

**Timezone offset caveat:** The daily rollup uses a local-time offset so that bucket boundaries align with midnight at the facility's local time rather than UTC midnight. The offset is baked in at view-creation time:

```sql
time_bucket(INTERVAL '1 day', timestamp, offset => INTERVAL '-3 hours') AS bucket
```

This offset is taken from `REPORT_TZ_OFFSET_HOURS` (default: **3**, i.e. UTC+3 Istanbul). **If `REPORT_TZ_OFFSET_HOURS` is changed after the view has been created, the `tag_readings_1d` view must be dropped and recreated** — otherwise the bucket boundaries in the view and the query-time reconstruction will be mismatched. This is documented in the code comment in `timescaledb.py`.

To recreate after an offset change:

```sql
DROP MATERIALIZED VIEW tag_readings_1d CASCADE;
-- Then restart the backend — init_daily_rollup() will recreate it with the new offset.
```

### 4.4 Report Archive Retention

| Setting | Default | Source |
|---|---|---|
| `REPORT_ARCHIVE_KEEP_DAYS` | **365** | `config.py` line `REPORT_ARCHIVE_KEEP_DAYS: int = 365` |

The application enforces this limit on `report_archive` rows (and their associated `file_path` files on disk). After 365 days, old archive records and generated files are eligible for cleanup by the scheduler.

### 4.5 Summary Table

| Data layer | Compression | Retention |
|---|---|---|
| `tag_readings` (raw) | After 7 days | Dropped after 90 days (`RAW_RETENTION_DAYS`) |
| `tag_readings_1m` CAGG | N/A | Indefinite |
| `tag_readings_5m` CAGG | N/A | Indefinite |
| `tag_readings_1h` CAGG | N/A | Indefinite |
| `tag_readings_1d` daily rollup | N/A | Indefinite (no retention policy) |
| `report_archive` rows + files | N/A | 365 days (`REPORT_ARCHIVE_KEEP_DAYS`) |

---

## Appendix A — Quick Reference

```text
PostgreSQL host:     localhost:5432
Database name:       scada_reporter
Default DB user:     scada
Docker volume:       pgdata
Grafana volume:      grafana-data
Portainer volume:    portainer-data
Readiness endpoint:  GET /ready (HTTP 200 = all checks pass)
Liveness endpoint:   GET /live  (always 200 if process is alive)
```

## Appendix B — Key Configuration Variables

| Variable | Default | Effect |
|---|---|---|
| `RAW_RETENTION_DAYS` | 90 | Days of raw `tag_readings` kept before TimescaleDB drops chunks |
| `REPORT_ARCHIVE_KEEP_DAYS` | 365 | Days report archive rows and generated files are retained |
| `REPORT_TZ_OFFSET_HOURS` | 3 | UTC offset for daily rollup bucket alignment (UTC+3 Istanbul) — changing requires recreating `tag_readings_1d` |
| `AUTO_CREATE_TABLES` | True (dev) / False (prod) | Set to `False` in production — schema managed by Alembic |
| `DATABASE_URL` | `postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter` | Override in `.env` for production |
