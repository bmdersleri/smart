#!/usr/bin/env bash
# backup.sh — EKONT SMART REPORT production backup
#
# Produces a timestamped backup directory containing:
#   - PostgreSQL logical dump (pg_dump --format=custom)
#   - Docker named-volume tarballs (pgdata, grafana-data)
#
# Usage:
#   ./scripts/backup.sh [--output-dir /path/to/backups] [--db-host localhost] \
#                       [--db-port 5432] [--db-user scada] [--db-name scada_reporter]
#
# Idempotent: re-running creates a new timestamped subdirectory each time.
# Does NOT delete old backups automatically (no rm -rf); prune manually or
# with a separate retention script.
#
# Dependencies: pg_dump, docker (for volume backups). Both are optional — the
# script skips a step and warns rather than aborting if a tool is absent.

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
OUTPUT_DIR="/backup/scada-reporter"
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="scada"
DB_NAME="scada_reporter"
PGDATA_VOLUME="pgdata"
GRAFANA_VOLUME="grafana-data"

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)  OUTPUT_DIR="$2";  shift 2 ;;
    --db-host)     DB_HOST="$2";     shift 2 ;;
    --db-port)     DB_PORT="$2";     shift 2 ;;
    --db-user)     DB_USER="$2";     shift 2 ;;
    --db-name)     DB_NAME="$2";     shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ── Setup ────────────────────────────────────────────────────────────────────
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEST="${OUTPUT_DIR}/${TIMESTAMP}"
mkdir -p "${DEST}"

echo "[backup] Starting backup → ${DEST}"
echo "[backup] $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ── 1. PostgreSQL logical dump ───────────────────────────────────────────────
DUMP_FILE="${DEST}/scada_reporter_${TIMESTAMP}.dump"

if command -v pg_dump > /dev/null 2>&1; then
  echo "[backup] pg_dump → ${DUMP_FILE}"
  pg_dump \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${DB_USER}" \
    --dbname="${DB_NAME}" \
    --no-owner \
    --no-privileges \
    --format=custom \
    --file="${DUMP_FILE}"
  echo "[backup] pg_dump done ($(du -sh "${DUMP_FILE}" | cut -f1))"
else
  echo "[backup] WARNING: pg_dump not found — skipping database dump" >&2
fi

# ── 2. Docker volume backup: pgdata ─────────────────────────────────────────
PGDATA_TAR="${DEST}/pgdata_${TIMESTAMP}.tar.gz"

if command -v docker > /dev/null 2>&1; then
  echo "[backup] Snapshotting Docker volume '${PGDATA_VOLUME}' → ${PGDATA_TAR}"
  # Note: the DB container is left running; TimescaleDB WAL makes the snapshot
  # consistent enough for DR purposes, but a cold snapshot (stop container first)
  # is safer. Stop manually before this step for a guaranteed-consistent copy.
  docker run --rm \
    -v "${PGDATA_VOLUME}:/data:ro" \
    -v "${DEST}:/backup" \
    alpine \
    tar czf "/backup/pgdata_${TIMESTAMP}.tar.gz" -C /data .
  echo "[backup] pgdata volume snapshot done"

  # ── 3. Docker volume backup: grafana-data ──────────────────────────────────
  GRAFANA_TAR="${DEST}/grafana_data_${TIMESTAMP}.tar.gz"
  echo "[backup] Snapshotting Docker volume '${GRAFANA_VOLUME}' → ${GRAFANA_TAR}"
  docker run --rm \
    -v "${GRAFANA_VOLUME}:/data:ro" \
    -v "${DEST}:/backup" \
    alpine \
    tar czf "/backup/grafana_data_${TIMESTAMP}.tar.gz" -C /data .
  echo "[backup] grafana-data volume snapshot done"
else
  echo "[backup] WARNING: docker not found — skipping volume snapshots" >&2
fi

# ── 4. Summary ───────────────────────────────────────────────────────────────
echo "[backup] Backup complete. Contents of ${DEST}:"
ls -lh "${DEST}"
echo "[backup] Done at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
