# Database Statistics on the Live Metrics Page — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan

## Problem

The Live Metrics ("Canlı Metrikler") page shows poller throughput and deadband
savings but nothing about the database itself. Operators want to see, in one
place: the database size, how many readings are stored, since when, recent
write volume (day/week/month), per-table row counts, the daily write rate, and
an estimated growth projection.

## Requirements (from brainstorming)

- **Metrics to show** (all four groups):
  1. Database **size**, total `tag_readings` count, **earliest** reading date.
  2. Last **24 hours / 7 days / 30 days** `tag_readings` counts.
  3. **Tag count** + per-table row counts (a curated table list).
  4. **Daily write rate** + estimated monthly disk growth.
- **Refresh:** a **manual "Yenile" (Refresh) button** — NOT auto-polling. The
  heavy `count(*)` over ~11M rows runs only on demand (initial load + button).
- Reuse the existing `dashboard` router + the Metrics page card/section style.

## Architecture

### Backend — `GET /dashboard/database` (`app/api/dashboard.py`)

Behind `get_current_user`. Computes (no server-side cache — on-demand only):

- **Size** (`size_bytes`): dialect-detected via `settings.DATABASE_URL`.
  - SQLite: the DB file path parsed from the URL
    (`sqlite+aiosqlite:///./scada_reporter.db` → `./scada_reporter.db`), summing
    `os.path.getsize` of the file plus its `-wal` and `-shm` siblings when they
    exist. An in-memory/`:memory:` or missing file → `0` (graceful).
  - PostgreSQL: `SELECT pg_database_size(current_database())`.
- **Total + earliest** (`total_readings`, `earliest`): `SELECT count(*) FROM
  tag_readings` and `SELECT min(timestamp) FROM tag_readings`; `earliest` is the
  ISO string or `null` when empty.
- **Recent counts** (`last_day`, `last_week`, `last_month`): `SELECT count(*)
  FROM tag_readings WHERE timestamp >= :cutoff` where each cutoff is computed in
  Python (`datetime.utcnow() - timedelta(days=1|7|30)`) and bound as a parameter
  (portable across SQLite/Postgres; uses the `ix_tag_readings_timestamp` index).
- **Tag count + per-table** (`tag_count`, `tables`): `count(*)` over a hardcoded
  allowlist of meaningful tables — `tag_readings`, `tags`, `lab_measurements`,
  `lab_samples`, `report_history`, `audit_logs`, `app_settings` — each returned
  as `{"name": str, "rows": int}`. The table list is a fixed constant (no user
  input → no injection).
- **Rate + growth** (`daily_rows`, `est_monthly_growth_bytes`): `daily_rows =
  last_day`; `est_monthly_growth_bytes = round((size_bytes / total_readings) *
  daily_rows * 30)` when `total_readings > 0`, else `0`.

Returns a single JSON object with all of the above. A missing table in the
allowlist (e.g. on an old schema) is counted as `0` rather than erroring.

### Frontend — Database section on `Metrics.tsx`

- New client function `getDatabaseStats()` → `api.get<DatabaseStats>('/dashboard/database')`.
- A TanStack Query with **no `refetchInterval`** (manual): `useQuery({ queryKey:
  ['database-stats'], queryFn: ..., refetchInterval: false })`, plus a "Yenile"
  button calling `refetch()`. Show a loading state while fetching.
- A "Veritabanı" (Database) section using the page's existing `StatCard`
  component: cards for Size, Total readings, Earliest date, Last 24h / 7d / 30d,
  Tag count, Daily rows, ~Monthly growth; plus a compact per-table row-count
  list.
- Pure formatters (unit-tested): `formatBytes(n)` → `"6.4 GB"` / `"512 MB"`;
  numbers via `toLocaleString(locale)`; the earliest date via the existing date
  rendering. i18n keys in the `metrics` namespace, all 5 languages.

## Testing (TDD)

- **Backend** (`tests/test_database_stats.py`): seed a few `tag_readings` (with
  recent + old timestamps) + `tags`; assert `total_readings`, `last_day` (only
  recent rows), `earliest` matches the oldest, `tag_count`, and that `tables`
  contains the allowlisted names with correct counts; an empty DB → `total 0`,
  `earliest null`, `est_monthly_growth_bytes 0` (no divide-by-zero). `size_bytes`
  is `0` on the in-memory test DB (file absent) — asserted as `>= 0`.
- **Frontend** (`src/pages/metricsDb.helper.test.ts`, vitest): `formatBytes`
  (bytes→GB/MB/KB boundaries) and any pure helper; plus `pnpm tsc -b` + `pnpm
  lint`.

## Verification

After implementation: open Live Metrics → the Database section shows the size,
total readings (~11M), earliest date (~2026-06-09), the day/week/month counts,
tag count, per-table rows, daily rate, and estimated growth; clicking "Yenile"
re-fetches.

## Out of scope (YAGNI)

- A historical size-trend chart.
- Per-table byte size (row counts only).
- Vacuum/optimize actions.
- Auto-polling (manual refresh only, by decision).
