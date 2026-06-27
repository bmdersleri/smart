# Database Statistics on the Live Metrics Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /dashboard/database` endpoint and a "Veritabanı" section on the Live Metrics page showing DB size, total/earliest readings, day/week/month counts, tag + per-table row counts, daily write rate, and estimated monthly growth — refreshed by a manual button.

**Architecture:** A new endpoint in the existing `dashboard` router computes the stats on demand (dialect-aware size, parameterized recent-count queries, a fixed table allowlist). The `Metrics.tsx` page gains a Database section driven by a non-polling TanStack Query with a "Yenile" refetch button, using pure formatters.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy async (`text()` queries) / `os.path`; React 19 / TypeScript / TanStack Query / hand-written axios.

## Global Constraints

- Python baseline **3.14**. Backend TDD per-file: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v` (from `scada-reporter/backend`; Python is `python`, venv `.venv/Scripts/python`).
- Lint/type gate `just check` before each task's final commit.
- Endpoint behind `get_current_user`, on the EXISTING `dashboard` router (prefix `/dashboard`, already mounted) — no main.py change.
- Recent-count cutoffs computed in Python (`datetime.utcnow() - timedelta`) and bound as query parameters — portable across SQLite/Postgres; never string-interpolated.
- Per-table counts use a FIXED table allowlist constant (no user input). The `f"SELECT count(*) FROM {table}"` over that constant list needs a `# nosec B608` justification comment (fixed allowlist, no user input).
- `size_bytes` is dialect-aware: SQLite → file size (+ `-wal`/`-shm`), `:memory:`/missing → `0`; Postgres → `pg_database_size(current_database())`.
- Manual refresh only — the frontend query has `refetchInterval: false` + a button calling `refetch()`. NO auto-polling.
- Frontend: NO `prettier --write`; hand-written axios (`api.get`, read `.data`); reuse the page's `StatCard`; i18n in the `metrics` namespace, all 5 languages.
- Branch `master`, commit directly (dev-phase). Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Commit discipline (drift-heavy repo):** `git checkout master` at start + before commit; put `-m "msg"` BEFORE the `--` separator: `git commit -m "<msg>" -- <files>`. `git add` NEW files first. NEVER `git add -A` / bare `git commit`.

---

## Task 1: Backend `GET /dashboard/database`

**Files:**
- Modify: `scada-reporter/backend/app/api/dashboard.py`
- Test: `scada-reporter/backend/tests/test_database_stats.py`

**Interfaces:**
- Produces: `GET /api/dashboard/database` → `{size_bytes, total_readings, earliest, last_day, last_week, last_month, tag_count, tables: [{name, rows}], daily_rows, est_monthly_growth_bytes}`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_database_stats.py`:

```python
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api.auth import get_current_user
from app.main import app
from app.models.tag import Tag, TagReading


def _as_user():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="u", role="operator", permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_database_stats_empty(client):
    _as_user()
    r = await client.get("/api/dashboard/database")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_readings"] == 0
    assert body["earliest"] is None
    assert body["est_monthly_growth_bytes"] == 0
    assert body["size_bytes"] >= 0
    names = {t["name"] for t in body["tables"]}
    assert "tag_readings" in names and "tags" in names


@pytest.mark.asyncio
async def test_database_stats_counts(client, db_session):
    tag = Tag(node_id="n1", name="T1")
    db_session.add(tag)
    await db_session.flush()
    now = datetime.utcnow()
    db_session.add(TagReading(tag_id=tag.id, value=1.0, quality=192, timestamp=now))
    db_session.add(TagReading(tag_id=tag.id, value=2.0, quality=192, timestamp=now - timedelta(days=10)))
    await db_session.commit()

    _as_user()
    r = await client.get("/api/dashboard/database")
    body = r.json()
    assert body["total_readings"] == 2
    assert body["last_day"] == 1      # only the recent row
    assert body["last_month"] == 2    # both within 30 days
    assert body["tag_count"] == 1
    assert body["earliest"] is not None
    tr = next(t for t in body["tables"] if t["name"] == "tag_readings")
    assert tr["rows"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_database_stats.py -p no:randomly -n0 -v`
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Implement the endpoint**

In `scada-reporter/backend/app/api/dashboard.py`, add `import os` at the top and `from app.core.config import settings` to the imports (the module imports `text`, `datetime`, `UTC`, `timedelta`, `get_db`, `get_current_user`, `AsyncSession` already). Then add the helpers + endpoint (after the existing `/metrics` endpoint):

```python
_DB_STAT_TABLES = [
    "tag_readings",
    "tags",
    "lab_measurements",
    "lab_samples",
    "report_history",
    "audit_logs",
    "app_settings",
]


def _sqlite_size_bytes(url: str) -> int:
    # sqlite+aiosqlite:///./scada_reporter.db  ->  ./scada_reporter.db
    path = url.split(":///")[-1]
    if not path or path == ":memory:":
        return 0
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


async def _table_count(db: AsyncSession, table: str) -> int:
    try:
        # nosec B608 - `table` is from the fixed _DB_STAT_TABLES allowlist, no user input
        result = await db.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        return int(result.scalar() or 0)
    except Exception:
        return 0  # table may not exist on an older schema


@router.get("/database")
async def database_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        size_bytes = _sqlite_size_bytes(url)
    else:
        size_bytes = int(
            (await db.execute(text("SELECT pg_database_size(current_database())"))).scalar() or 0
        )

    total = int((await db.execute(text("SELECT count(*) FROM tag_readings"))).scalar() or 0)
    earliest = (await db.execute(text("SELECT min(timestamp) FROM tag_readings"))).scalar()

    now = datetime.utcnow()
    sql_recent = text("SELECT count(*) FROM tag_readings WHERE timestamp >= :c")
    last_day = int((await db.execute(sql_recent, {"c": now - timedelta(days=1)})).scalar() or 0)
    last_week = int((await db.execute(sql_recent, {"c": now - timedelta(days=7)})).scalar() or 0)
    last_month = int((await db.execute(sql_recent, {"c": now - timedelta(days=30)})).scalar() or 0)

    tag_count = int((await db.execute(text("SELECT count(*) FROM tags"))).scalar() or 0)

    tables = []
    for tbl in _DB_STAT_TABLES:
        tables.append({"name": tbl, "rows": await _table_count(db, tbl)})

    daily_rows = last_day
    est_monthly_growth = (
        round((size_bytes / total) * daily_rows * 30) if total > 0 else 0
    )

    return {
        "size_bytes": size_bytes,
        "total_readings": total,
        "earliest": str(earliest) if earliest is not None else None,
        "last_day": last_day,
        "last_week": last_week,
        "last_month": last_month,
        "tag_count": tag_count,
        "tables": tables,
        "daily_rows": daily_rows,
        "est_monthly_growth_bytes": est_monthly_growth,
    }
```

> NOTE: `datetime.utcnow()` is used to match the existing module's naive-UTC comparison against `tag_readings.timestamp` (the column is naive). If ruff flags `utcnow`, keep it consistent with the rest of `dashboard.py` (which already compares against naive timestamps). The `# noqa: S608` / `# nosec B608` on the dynamic-table query is justified by the fixed allowlist.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_database_stats.py -p no:randomly -n0 -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Checks + commit**

Run: `.venv/Scripts/python -m ruff check app/api/dashboard.py` (clean) then `just check` (confirm no NEW failure beyond the pre-existing bandit set).

```bash
git checkout master
git commit -m "feat(dashboard): GET /dashboard/database statistics endpoint" -- scada-reporter/backend/app/api/dashboard.py scada-reporter/backend/tests/test_database_stats.py
```

---

## Task 2: Frontend Database section + verification

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Create: `scada-reporter/frontend/src/pages/metricsDb.helper.ts` (+ `.test.ts`)
- Modify: `scada-reporter/frontend/src/pages/Metrics.tsx`
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/metrics.json`
- Modify: `docs/lab-data-entry.md`? No — this is metrics, not lab. (No doc change required; the feature is self-evident on the page.)

**Interfaces:**
- Consumes: Task 1 endpoint.
- Produces: `getDatabaseStats()`; `formatBytes(n)`.

- [ ] **Step 1: Add the client function + type**

In `scada-reporter/frontend/src/api/client.ts`, add (near `getMetrics`):

```ts
export interface DatabaseStats {
  size_bytes: number
  total_readings: number
  earliest: string | null
  last_day: number
  last_week: number
  last_month: number
  tag_count: number
  tables: { name: string; rows: number }[]
  daily_rows: number
  est_monthly_growth_bytes: number
}

export const getDatabaseStats = () => api.get<DatabaseStats>('/dashboard/database')
```

- [ ] **Step 2: Write the failing helper test**

Create `scada-reporter/frontend/src/pages/metricsDb.helper.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatBytes } from './metricsDb.helper'

describe('formatBytes', () => {
  it('0 bytes', () => expect(formatBytes(0)).toBe('0 B'))
  it('bytes', () => expect(formatBytes(512)).toBe('512 B'))
  it('KB', () => expect(formatBytes(2048)).toBe('2.0 KB'))
  it('MB', () => expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB'))
  it('GB', () => expect(formatBytes(6.4 * 1024 * 1024 * 1024)).toBe('6.4 GB'))
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/metricsDb.helper.test.ts`
Expected: FAIL — cannot resolve `./metricsDb.helper`.

- [ ] **Step 4: Implement the helper**

Create `scada-reporter/frontend/src/pages/metricsDb.helper.ts`:

```ts
// Human-readable byte size: B / KB / MB / GB / TB (1 decimal above bytes).
export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return i === 0 ? `${Math.round(v)} B` : `${v.toFixed(1)} ${units[i]}`
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm vitest run src/pages/metricsDb.helper.test.ts`
Expected: PASS (5 passed).

- [ ] **Step 6: Add i18n keys (all 5 languages)**

In each `src/i18n/locales/{en,tr,ru,de,ar}/metrics.json`, add the same keys (English shown; Turkish in parentheses — translate ru/de/ar):

```json
{
  "db_title": "Database",
  "db_refresh": "Refresh",
  "db_size": "Size",
  "db_total": "Total readings",
  "db_earliest": "Oldest record",
  "db_last_day": "Last 24h",
  "db_last_week": "Last 7d",
  "db_last_month": "Last 30d",
  "db_tags": "Tags",
  "db_daily": "Rows/day",
  "db_growth": "Est. monthly growth",
  "db_tables": "Rows per table"
}
```
Turkish values: `"Veritabanı"`, `"Yenile"`, `"Boyut"`, `"Toplam kayıt"`, `"En eski kayıt"`, `"Son 24s"`, `"Son 7g"`, `"Son 30g"`, `"Tag sayısı"`, `"Satır/gün"`, `"Tahmini aylık büyüme"`, `"Tablo başına satır"`.

- [ ] **Step 7: Add the Database section to Metrics.tsx**

In `scada-reporter/frontend/src/pages/Metrics.tsx`:
1. Import: add `getDatabaseStats` (and the type if needed) to the `'../api/client'` import; `import { formatBytes } from './metricsDb.helper'`.
2. Add a NON-polling query: `const { data: dbStats, isFetching: dbFetching, refetch: refetchDb } = useQuery({ queryKey: ['database-stats'], queryFn: () => getDatabaseStats().then((r) => r.data), refetchInterval: false })`.
3. Add a "Veritabanı" section (place it after the existing metric cards / deadband section, matching the page's section style). Header with the title + a "Yenile" button (`onClick={() => refetchDb()}`, disabled while `dbFetching`, label `t('db_refresh')`). When `dbStats` is present, render a `StatCard` grid: Size = `formatBytes(dbStats.size_bytes)`, Total = `dbStats.total_readings.toLocaleString(i18n.language)`, Oldest = the `earliest` date (render with `new Date(dbStats.earliest).toLocaleDateString(i18n.language)` guarded for null → '—'), Last 24h/7d/30d, Tags, Rows/day, Est. growth = `formatBytes(dbStats.est_monthly_growth_bytes)`. Below the cards, a compact list mapping `dbStats.tables` to `name: rows.toLocaleString()`. All labels via `t('db_*')`.

Keep the compact style; do not run prettier.

- [ ] **Step 8: Verify**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/metricsDb.helper.test.ts` (5 pass), `pnpm tsc -b` (0 errors), `pnpm lint` (clean on changed files).

- [ ] **Step 9: Commit + push**

```bash
git checkout master
git commit -m "feat(metrics): database statistics section with manual refresh" -- scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/metricsDb.helper.ts scada-reporter/frontend/src/pages/metricsDb.helper.test.ts scada-reporter/frontend/src/pages/Metrics.tsx scada-reporter/frontend/src/i18n/locales/en/metrics.json scada-reporter/frontend/src/i18n/locales/tr/metrics.json scada-reporter/frontend/src/i18n/locales/ru/metrics.json scada-reporter/frontend/src/i18n/locales/de/metrics.json scada-reporter/frontend/src/i18n/locales/ar/metrics.json
git push origin master
```

- [ ] **Step 10: E2E verification (browser)** — requires the backend restarted to load the new endpoint (NSSM `EkontBackend`, no hot-reload; needs elevation) and the frontend rebuilt (`pnpm build`, EkontFrontend serves dist live).
1. Open Live Metrics → the Database section shows Size, Total readings (~11M), Oldest date, Last 24h/7d/30d, Tags, Rows/day, Est. growth, and the per-table list.
2. Click "Yenile" → the section re-fetches (brief loading, values refresh).

---

## Self-Review

**Spec coverage:**
- Size + total + earliest → Task 1 (`size_bytes`, `total_readings`, `earliest`). ✓
- Day/week/month → Task 1 (`last_day/week/month`, parameterized cutoffs). ✓
- Tag count + per-table → Task 1 (`tag_count`, `tables` allowlist). ✓
- Daily rate + est. growth → Task 1 (`daily_rows`, `est_monthly_growth_bytes`). ✓
- Manual refresh (no polling) → Task 2 (`refetchInterval: false` + "Yenile" button). ✓
- Dialect-aware size (SQLite file / Postgres `pg_database_size`) → Task 1. ✓
- `formatBytes` + i18n 5 langs → Task 2. ✓
- Out-of-scope (size-trend chart, per-table bytes, vacuum, auto-poll) → not in any task. ✓

**Placeholder scan:** No "TBD". Task 2 step 7 describes the Metrics.tsx section wiring in prose (the page is large; match its existing `StatCard`/section markup) with the exact query config + card values; the testable logic (`formatBytes`) has full code + tests.

**Type consistency:** `getDatabaseStats()` returns `AxiosResponse<DatabaseStats>` (caller reads `.data`); the `DatabaseStats` interface fields match the endpoint's returned keys exactly (`size_bytes`, `total_readings`, `earliest`, `last_day/week/month`, `tag_count`, `tables[{name,rows}]`, `daily_rows`, `est_monthly_growth_bytes`). `formatBytes(n: number): string` matches its test.
