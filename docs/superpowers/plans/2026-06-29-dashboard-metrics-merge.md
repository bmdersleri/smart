# Dashboard + Live Metrics Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the standalone `/metrics` ("Canlı Metrikler") page into the Dashboard page as two new tabs (System + Database), and remove the old page/route/nav.

**Architecture:** Extract the current `pages/Metrics.tsx` sections into two new tab components under `pages/dashboard/` (`SystemTab`, `DatabaseTab`), sharing a small presentational helper. Wire them into the existing local-state tab bar in `Dashboard.tsx`. Gate each tab's data fetching on an `active` prop (the established `pages/dashboard/` pattern) so polling/SSE only run when the tab is open. Redirect `/metrics` → `/` and drop the sidebar entry.

**Tech Stack:** React 19, TanStack Query, react-i18next, Vite, Vitest + Testing Library, Tailwind v4.

## Global Constraints

- Frontend only — no backend or API-client changes. Endpoints `getMetrics`, `getDeadbandSavings`, `getDatabaseStats`, and the log SSE (`useLogStream`) are untouched.
- Section markup moves verbatim (no restyling). Only behavioral change: `active`-gated polling.
- i18n: section strings stay in the `metrics` namespace; only the two new tab labels go in the `dashboard` namespace, across all 5 locales (en/tr/ru/de/ar).
- Follow the existing `pages/dashboard/` convention: each tab is a default-export component taking `{ active: boolean }` and gating queries with `enabled: active`.
- Run frontend tests from `scada-reporter/frontend` with `pnpm test`.

## File Structure

- Create `scada-reporter/frontend/src/pages/dashboard/metricsShared.tsx` — `StatCard`, `fmtMs`, `fmtPct` (presentational, shared by both new tabs).
- Create `scada-reporter/frontend/src/pages/dashboard/SystemTab.tsx` — poller stats + deadband + latency table + live console.
- Create `scada-reporter/frontend/src/pages/dashboard/DatabaseTab.tsx` — DB stats + manual refresh.
- Modify `scada-reporter/frontend/src/pages/Dashboard.tsx` — add the two tabs.
- Modify `scada-reporter/frontend/src/App.tsx` — `/metrics` → redirect.
- Modify `scada-reporter/frontend/src/components/Layout.tsx` — drop nav item.
- Modify 5 × `scada-reporter/frontend/src/i18n/locales/<lng>/dashboard.json` — add `tab_system`, `tab_database`.
- Delete `scada-reporter/frontend/src/pages/Metrics.tsx`.
- Move `scada-reporter/frontend/src/pages/Metrics.console.test.tsx` → `scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx`.
- Create `scada-reporter/frontend/src/pages/dashboard/DatabaseTab.test.tsx`.
- Modify `scada-reporter/frontend/src/pages/dashboard/Dashboard.i18n.test.tsx` — mock new tabs, assert new labels.
- `scada-reporter/frontend/src/pages/metricsDb.helper.ts` + `metricsDb.helper.test.ts` — unchanged.

---

### Task 1: Shared presentational helper

**Files:**
- Create: `scada-reporter/frontend/src/pages/dashboard/metricsShared.tsx`

**Interfaces:**
- Produces:
  - `StatCard({ label: string; value: string; sub?: string; accent?: string }): JSX.Element`
  - `fmtMs(s: number | null): string`
  - `fmtPct(r: number | null): string`

- [ ] **Step 1: Create the shared helper file**

```tsx
// Presentational helpers shared by the Dashboard System + Database tabs.

export function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 font-mono ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

export function fmtMs(s: number | null): string {
  if (s === null) return '—'
  return `${(s * 1000).toFixed(1)} ms`
}

export function fmtPct(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(2)} %`
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd scada-reporter/frontend && pnpm tsc --noEmit`
Expected: PASS (no errors). The file is not yet imported anywhere — that's fine.

- [ ] **Step 3: Commit**

```bash
git add scada-reporter/frontend/src/pages/dashboard/metricsShared.tsx
git commit -m "feat(dashboard): add shared metrics stat helpers"
```

---

### Task 2: SystemTab component

**Files:**
- Create: `scada-reporter/frontend/src/pages/dashboard/SystemTab.tsx`
- Move + retarget test: `scada-reporter/frontend/src/pages/Metrics.console.test.tsx` → `scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx`

**Interfaces:**
- Consumes: `StatCard`, `fmtMs`, `fmtPct` from `./metricsShared` (Task 1); `getMetrics`, `getDeadbandSavings`, `MetricsSummary` from `../../api/client`; `useSortable` from `../../hooks/useSortable`; `SortHeader` from `../../components/SortHeader`; `useLogStream`, `LogLine` from `../../hooks/useLogStream`.
- Produces: `export default function SystemTab({ active }: { active: boolean }): JSX.Element`

- [ ] **Step 1: Write the failing test (move + retarget the console test)**

Create `scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx` and delete the old `scada-reporter/frontend/src/pages/Metrics.console.test.tsx`:

```tsx
// scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import '../../i18n' // initialise i18n so translations resolve in test env

// Mock the hook so the panel renders deterministically.
vi.mock('../../hooks/useLogStream', () => ({
  useLogStream: () => ({
    lines: [
      { seq: 1, ts: '2026-06-17T10:00:00Z', level: 'INFO', levelno: 20, name: 'app.poller', msg: 'tick ok' },
      { seq: 2, ts: '2026-06-17T10:00:01Z', level: 'ERROR', levelno: 40, name: 'app', msg: 'boom' },
    ],
    clear: vi.fn(),
  }),
}))

// Stub the metrics queries so the tab body mounts without a backend.
vi.mock('../../api/client', () => ({
  getMetrics: () => Promise.resolve({ data: { rows_written_total: 0, bad_quality_total: 0, bad_ratio: null, tick_count: 0, tick_avg_seconds: null, plcs: [] } }),
  getDeadbandSavings: () => Promise.resolve({ data: null }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SystemTab from './SystemTab'

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SystemTab active={true} />
    </QueryClientProvider>,
  )
}

describe('SystemTab live console', () => {
  it('renders streamed log lines', async () => {
    renderTab()
    expect(await screen.findByText('tick ok')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('shows the console title', async () => {
    renderTab()
    expect(await screen.findByText('Live Backend Console')).toBeInTheDocument()
  })
})
```

Then remove the old file:

```bash
git rm scada-reporter/frontend/src/pages/Metrics.console.test.tsx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test SystemTab.console`
Expected: FAIL — cannot resolve `./SystemTab` (module does not exist yet).

- [ ] **Step 3: Create SystemTab.tsx**

```tsx
import { useRef, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getMetrics, getDeadbandSavings } from '../../api/client'
import type { MetricsSummary } from '../../api/client'
import { useSortable } from '../../hooks/useSortable'
import SortHeader from '../../components/SortHeader'
import { useLogStream } from '../../hooks/useLogStream'
import type { LogLine } from '../../hooks/useLogStream'
import { StatCard, fmtMs, fmtPct } from './metricsShared'

const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-400',
  WARNING: 'text-amber-400',
  INFO: 'text-gray-400',
  DEBUG: 'text-gray-600',
}

function LiveConsole({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const [level, setLevel] = useState('INFO')
  const [paused, setPaused] = useState(false)
  const { lines, clear } = useLogStream(level, active && !paused)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new lines unless paused.
  useEffect(() => {
    if (!paused && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [lines, paused])

  const fmtTime = (ts: string) => {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toLocaleTimeString(i18n.language)
  }

  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-edge flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-white">{t('console_title')}</h2>
          <p className="text-xs text-gray-500">{t('console_sub')}</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-xs text-gray-200"
          >
            <option value="INFO">{t('filter_all')}</option>
            <option value="WARNING">{t('filter_warning')}</option>
            <option value="ERROR">{t('filter_error')}</option>
          </select>
          <button
            onClick={() => setPaused((p) => !p)}
            className="px-2 py-1 text-xs rounded border border-edge-strong text-gray-200 hover:bg-white/5"
          >
            {paused ? t('btn_resume') : t('btn_pause')}
          </button>
          <button
            onClick={clear}
            className="px-2 py-1 text-xs rounded border border-edge-strong text-gray-200 hover:bg-white/5"
          >
            {t('btn_clear')}
          </button>
        </div>
      </div>
      <div ref={bodyRef} className="h-72 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
        {lines.length === 0 && (
          <p className="text-gray-600 text-center py-8">{t('console_empty')}</p>
        )}
        {lines.map((l: LogLine) => (
          <div key={l.seq} className="flex gap-2 whitespace-pre-wrap break-all">
            <span className="text-gray-600 shrink-0">{fmtTime(l.ts)}</span>
            <span className={`shrink-0 w-16 ${LEVEL_COLOR[l.level] ?? 'text-gray-400'}`}>{l.level}</span>
            <span className="text-gray-500 shrink-0">{l.name}</span>
            <span className={LEVEL_COLOR[l.level] ?? 'text-gray-300'}>{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function SystemTab({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const { data, isLoading, isError } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => getMetrics().then((r) => r.data),
    enabled: active,
    refetchInterval: active ? 2000 : false,
  })

  const { data: savings } = useQuery({
    queryKey: ['deadbandSavings'],
    queryFn: () => getDeadbandSavings(24).then((r) => r.data),
    enabled: active,
    refetchInterval: active ? 10000 : false,
  })

  const m: MetricsSummary | undefined = data
  const maxAvg = m?.plcs.reduce((acc, p) => Math.max(acc, p.avg_seconds ?? 0), 0) || 0
  const badAccent =
    m?.bad_ratio == null ? 'text-white' : m.bad_ratio > 0.05 ? 'text-red-400' : 'text-green-400'

  // default: slowest PLC on top; clicking a header re-sorts
  const byAvg = [...(m?.plcs ?? [])].sort((a, b) => (b.avg_seconds ?? 0) - (a.avg_seconds ?? 0))
  const { sorted: plcRows, sort, toggle } = useSortable(byAvg)

  return (
    <div className="space-y-6">
      {isLoading && <div className="text-center py-16 text-gray-500">{t('common:loading')}</div>}
      {isError && <div className="text-center py-16 text-red-400">{t('load_error')}</div>}

      {m && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('rows_written')} value={m.rows_written_total.toLocaleString(i18n.language)} sub={t('rows_written_sub')} accent="text-cyan-300" />
            <StatCard label={t('bad_quality')} value={m.bad_quality_total.toLocaleString(i18n.language)} sub={t('bad_quality_sub')} accent={badAccent} />
            <StatCard label={t('bad_ratio')} value={fmtPct(m.bad_ratio)} sub={t('bad_ratio_sub')} accent={badAccent} />
            <StatCard label={t('avg_tick')} value={fmtMs(m.tick_avg_seconds)} sub={t('avg_tick_sub', { value: m.tick_count.toLocaleString(i18n.language) })} accent="text-blue-300" />
          </div>

          {/* Deadband (report-by-exception) data savings — last 24 hours, dynamic */}
          {savings && (
            <div className="bg-gradient-to-br from-emerald-950/40 to-gray-900 border border-emerald-800/40 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-medium text-white flex items-center gap-2">
                    <span className="text-emerald-400">♻</span> {t('deadband_title')}
                  </h2>
                  <p className="text-xs text-gray-500">
                    {t('deadband_sub', { hours: savings.window_hours, tags: savings.deadband_tags.toLocaleString(i18n.language) })}
                  </p>
                </div>
                <div className="text-end">
                  <p className="text-4xl font-bold font-mono text-emerald-400">
                    {savings.savings_pct === null ? '—' : `${savings.savings_pct}%`}
                  </p>
                  <p className="text-xs text-gray-500">{t('write_savings')}</p>
                </div>
              </div>

              {/* savings bar: written (actual) vs prevented (savings) */}
              <div className="h-3 bg-surface-sunken rounded-full overflow-hidden flex mb-2">
                <div
                  className="h-full bg-emerald-500"
                  style={{ width: `${savings.savings_pct ?? 0}%` }}
                  title={t('rows_prevented_bar', { value: savings.saved_rows.toLocaleString(i18n.language) })}
                />
                <div className="h-full bg-cyan-600/70 flex-1" title={t('rows_written_bar', { value: savings.actual_rows.toLocaleString(i18n.language) })} />
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                <StatCard label={t('rows_prevented')} value={savings.saved_rows.toLocaleString(i18n.language)} sub={t('rows_prevented_sub', { hours: savings.window_hours })} accent="text-emerald-400" />
                <StatCard label={t('rows_written_db')} value={savings.actual_rows.toLocaleString(i18n.language)} sub={t('rows_written_db_sub')} accent="text-cyan-300" />
                <StatCard label={t('without_deadband')} value={savings.expected_rows.toLocaleString(i18n.language)} sub={t('without_deadband_sub')} accent="text-gray-300" />
                <StatCard label={t('daily_savings')} value={`~${savings.saved_rows_per_day.toLocaleString(i18n.language)}`} sub={t('daily_savings_sub')} accent="text-emerald-300" />
              </div>
            </div>
          )}

          <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden">
            <div className="px-4 py-3 border-b border-edge">
              <h2 className="text-sm font-medium text-white">{t('read_latency_title')}</h2>
              <p className="text-xs text-gray-500">{t('read_latency_sub', { value: m.plcs.length })}</p>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wide">
                  <SortHeader label={t('col_name')} sortKey="name" sort={sort} onToggle={toggle} />
                  <SortHeader label={t('col_ip')} sortKey="plc" sort={sort} onToggle={toggle} />
                  <SortHeader label={t('col_tag_count')} sortKey="tag_count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label={t('col_read_count')} sortKey="count" sort={sort} onToggle={toggle} align="right" />
                  <SortHeader label={t('col_avg_time')} sortKey="avg_seconds" sort={sort} onToggle={toggle} align="right" />
                  <th className="px-4 py-2 text-start w-1/4">{t('col_latency')}</th>
                </tr>
              </thead>
              <tbody>
                {plcRows
                  .map((p) => {
                    const pct = maxAvg > 0 ? ((p.avg_seconds ?? 0) / maxAvg) * 100 : 0
                    const slow = (p.avg_seconds ?? 0) > 0.5
                    return (
                      <tr key={p.plc} className="border-t border-edge hover:bg-white/5/40">
                        <td className="px-4 py-2 text-sm text-white">{p.name || '—'}</td>
                        <td className="px-4 py-2 text-sm font-mono text-gray-400">{p.plc}</td>
                        <td className="px-4 py-2 text-sm text-end text-gray-300 font-mono">{p.tag_count.toLocaleString(i18n.language)}</td>
                        <td className="px-4 py-2 text-sm text-end text-gray-400 font-mono">{p.count.toLocaleString(i18n.language)}</td>
                        <td className={`px-4 py-2 text-sm text-end font-mono ${slow ? 'text-red-400' : 'text-gray-200'}`}>{fmtMs(p.avg_seconds)}</td>
                        <td className="px-4 py-2">
                          <div className="h-2 bg-surface-sunken rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${slow ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${pct}%` }} />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                {m.plcs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">
                      {t('empty_plcs')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <LiveConsole active={active} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test SystemTab.console`
Expected: PASS — both tests green ("tick ok", "boom", "Live Backend Console").

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/dashboard/SystemTab.tsx scada-reporter/frontend/src/pages/dashboard/SystemTab.console.test.tsx
git rm scada-reporter/frontend/src/pages/Metrics.console.test.tsx
git commit -m "feat(dashboard): extract Metrics system section into SystemTab"
```

---

### Task 3: DatabaseTab component

**Files:**
- Create: `scada-reporter/frontend/src/pages/dashboard/DatabaseTab.tsx`
- Test: `scada-reporter/frontend/src/pages/dashboard/DatabaseTab.test.tsx`

**Interfaces:**
- Consumes: `StatCard` from `./metricsShared` (Task 1); `getDatabaseStats` from `../../api/client`; `formatBytes` from `../metricsDb.helper`.
- Produces: `export default function DatabaseTab({ active }: { active: boolean }): JSX.Element`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/frontend/src/pages/dashboard/DatabaseTab.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import '../../i18n'

// Stub the DB-stats query so the tab renders without a backend.
vi.mock('../../api/client', () => ({
  getDatabaseStats: () => Promise.resolve({
    data: {
      size_bytes: 1024,
      total_readings: 42,
      total_is_estimate: false,
      earliest: '2026-06-01T00:00:00Z',
      tag_count: 7,
      last_day: 1,
      last_week: 2,
      last_month: 3,
      daily_rows: 4,
      est_monthly_growth_bytes: 2048,
      tables: [{ name: 'tag_readings', rows: 42 }],
    },
  }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DatabaseTab from './DatabaseTab'

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DatabaseTab active={true} />
    </QueryClientProvider>,
  )
}

describe('DatabaseTab', () => {
  it('renders DB stats once loaded', async () => {
    renderTab()
    expect(await screen.findByText('1.0 KB')).toBeInTheDocument()
    expect(screen.getByText('tag_readings')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test DatabaseTab`
Expected: FAIL — cannot resolve `./DatabaseTab`.

- [ ] **Step 3: Create DatabaseTab.tsx**

```tsx
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getDatabaseStats } from '../../api/client'
import { formatBytes } from '../metricsDb.helper'
import { StatCard } from './metricsShared'

export default function DatabaseTab({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation(['metrics', 'common'])
  const { data: dbStats, isFetching: dbFetching, refetch: refetchDb } = useQuery({
    queryKey: ['database-stats'],
    queryFn: () => getDatabaseStats().then((r) => r.data),
    enabled: active,
    refetchInterval: false,
  })

  return (
    <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-edge flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-white">{t('db_title')}</h2>
        </div>
        <button
          onClick={() => refetchDb()}
          disabled={dbFetching}
          className="px-2 py-1 text-xs rounded border border-edge-strong text-gray-200 hover:bg-white/5 disabled:opacity-50"
        >
          {t('db_refresh')}
        </button>
      </div>
      {dbStats && (
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('db_size')} value={formatBytes(dbStats.size_bytes)} accent="text-blue-300" />
            <StatCard label={t('db_total')} value={`${dbStats.total_is_estimate ? '~' : ''}${dbStats.total_readings.toLocaleString(i18n.language)}`} accent="text-cyan-300" />
            <StatCard label={t('db_earliest')} value={dbStats.earliest ? new Date(dbStats.earliest).toLocaleDateString(i18n.language) : '—'} />
            <StatCard label={t('db_tags')} value={dbStats.tag_count.toLocaleString(i18n.language)} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label={t('db_last_day')} value={dbStats.last_day.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_last_week')} value={dbStats.last_week.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_last_month')} value={dbStats.last_month.toLocaleString(i18n.language)} accent="text-gray-300" />
            <StatCard label={t('db_daily')} value={dbStats.daily_rows.toLocaleString(i18n.language)} accent="text-gray-300" />
          </div>
          <StatCard label={t('db_growth')} value={formatBytes(dbStats.est_monthly_growth_bytes)} accent="text-emerald-300" />
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">{t('db_tables')}</p>
            <ul className="space-y-1">
              {dbStats.tables.map((tbl) => (
                <li key={tbl.name} className="flex items-center justify-between text-xs font-mono">
                  <span className="text-gray-400">{tbl.name}</span>
                  <span className="text-gray-200">{tbl.rows.toLocaleString(i18n.language)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test DatabaseTab`
Expected: PASS — "1.0 KB" and "tag_readings" found.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/dashboard/DatabaseTab.tsx scada-reporter/frontend/src/pages/dashboard/DatabaseTab.test.tsx
git commit -m "feat(dashboard): extract Metrics DB section into DatabaseTab"
```

---

### Task 4: Wire tabs into Dashboard, add i18n labels, redirect route, drop nav, delete Metrics

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Dashboard.tsx`
- Modify: `scada-reporter/frontend/src/i18n/locales/en/dashboard.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/tr/dashboard.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ru/dashboard.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/de/dashboard.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ar/dashboard.json`
- Modify: `scada-reporter/frontend/src/App.tsx`
- Modify: `scada-reporter/frontend/src/components/Layout.tsx`
- Modify: `scada-reporter/frontend/src/pages/dashboard/Dashboard.i18n.test.tsx`
- Delete: `scada-reporter/frontend/src/pages/Metrics.tsx`

**Interfaces:**
- Consumes: `SystemTab` (Task 2), `DatabaseTab` (Task 3).

- [ ] **Step 1: Add the two tab labels to all 5 dashboard.json locales**

`en/dashboard.json` — add after the `"tab_tags"` line:

```json
  "tab_system": "System",
  "tab_database": "Database",
```

`tr/dashboard.json`:

```json
  "tab_system": "Sistem",
  "tab_database": "Veritabanı",
```

`ru/dashboard.json`:

```json
  "tab_system": "Система",
  "tab_database": "База данных",
```

`de/dashboard.json`:

```json
  "tab_system": "System",
  "tab_database": "Datenbank",
```

`ar/dashboard.json`:

```json
  "tab_system": "النظام",
  "tab_database": "قاعدة البيانات",
```

(Place each pair right after that locale's `"tab_tags"` entry. Keep JSON valid — trailing comma only if more keys follow, which they do.)

- [ ] **Step 2: Update the Dashboard.i18n test to expect the new tabs (failing test)**

Replace `scada-reporter/frontend/src/pages/dashboard/Dashboard.i18n.test.tsx` with:

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from '../../i18n'
import Dashboard from '../Dashboard'

// The tab bar is static; mock the data-heavy tab bodies so Dashboard renders without providers.
vi.mock('../dashboard/OverviewTab', () => ({ default: () => null }))
vi.mock('../dashboard/WatchlistTab', () => ({ default: () => null }))
vi.mock('../dashboard/AllTagsTab', () => ({ default: () => null }))
vi.mock('../dashboard/SystemTab', () => ({ default: () => null }))
vi.mock('../dashboard/DatabaseTab', () => ({ default: () => null }))
// Dashboard reads live connection status via a TanStack-Query hook; stub it so the
// test needs no QueryClientProvider (it only asserts the static tab labels).
vi.mock('../../hooks/useLiveDashboard', () => ({ useLiveDashboard: () => ({ status: 'connected' }) }))

describe('Dashboard i18n', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('renders the English tab labels', () => {
    render(<Dashboard />)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'System' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Database' })).toBeTruthy()
  })

  it('renders the Turkish tab label after switch', async () => {
    await i18n.changeLanguage('tr')
    render(<Dashboard />)
    expect(screen.getByRole('button', { name: 'Özet' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Sistem' })).toBeTruthy()
  })

  it('shows no raw translation keys', () => {
    render(<Dashboard />)
    expect(document.body.textContent).not.toMatch(/dashboard:/)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test Dashboard.i18n`
Expected: FAIL — `System` / `Database` buttons not found (Dashboard does not render them yet).

- [ ] **Step 4: Wire the two tabs into Dashboard.tsx**

In `scada-reporter/frontend/src/pages/Dashboard.tsx`:

Add imports after the existing tab imports (lines 4-6):

```tsx
import AllTagsTab from './dashboard/AllTagsTab'
import OverviewTab from './dashboard/OverviewTab'
import WatchlistTab from './dashboard/WatchlistTab'
import SystemTab from './dashboard/SystemTab'
import DatabaseTab from './dashboard/DatabaseTab'
```

Change the `Tab` type and `TABS` array:

```tsx
type Tab = 'overview' | 'watchlist' | 'tags' | 'system' | 'database'

const TABS: { id: Tab; labelKey: string }[] = [
  { id: 'overview', labelKey: 'tab_overview' },
  { id: 'watchlist', labelKey: 'tab_watchlist' },
  { id: 'tags', labelKey: 'tab_tags' },
  { id: 'system', labelKey: 'tab_system' },
  { id: 'database', labelKey: 'tab_database' },
]
```

Add the two render lines after the existing tab-content block (after line 67):

```tsx
      {activeTab === 'overview' && <OverviewTab active={activeTab === 'overview'} />}
      {activeTab === 'watchlist' && <WatchlistTab active={activeTab === 'watchlist'} />}
      {activeTab === 'tags' && <AllTagsTab active={activeTab === 'tags'} />}
      {activeTab === 'system' && <SystemTab active={activeTab === 'system'} />}
      {activeTab === 'database' && <DatabaseTab active={activeTab === 'database'} />}
```

- [ ] **Step 5: Run the Dashboard test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test Dashboard.i18n`
Expected: PASS — all five tab labels render; no raw keys.

- [ ] **Step 6: Redirect the `/metrics` route**

In `scada-reporter/frontend/src/App.tsx`:

Remove the import line:

```tsx
import Metrics from './pages/Metrics'
```

Replace the route (currently `<Route path="metrics" element={<Metrics />} />`) with:

```tsx
            <Route path="metrics" element={<Navigate to="/" replace />} />
```

(`Navigate` is already imported from `react-router-dom` at the top of the file.)

- [ ] **Step 7: Remove the sidebar nav entry**

In `scada-reporter/frontend/src/components/Layout.tsx`, delete this line from the nav array:

```tsx
  { to: '/metrics', labelKey: 'nav_metrics' },
```

- [ ] **Step 8: Delete the old Metrics page**

```bash
git rm scada-reporter/frontend/src/pages/Metrics.tsx
```

- [ ] **Step 9: Type-check and run the full frontend suite**

Run: `cd scada-reporter/frontend && pnpm tsc --noEmit && pnpm test`
Expected: tsc clean (no dangling `./pages/Metrics` import). All tests pass. If any other test imports `./pages/Metrics` or asserts a `/metrics` sidebar link, update it to match the redirect/removal.

- [ ] **Step 10: Commit**

```bash
git add scada-reporter/frontend/src/pages/Dashboard.tsx \
        scada-reporter/frontend/src/i18n/locales/en/dashboard.json \
        scada-reporter/frontend/src/i18n/locales/tr/dashboard.json \
        scada-reporter/frontend/src/i18n/locales/ru/dashboard.json \
        scada-reporter/frontend/src/i18n/locales/de/dashboard.json \
        scada-reporter/frontend/src/i18n/locales/ar/dashboard.json \
        scada-reporter/frontend/src/App.tsx \
        scada-reporter/frontend/src/components/Layout.tsx \
        scada-reporter/frontend/src/pages/dashboard/Dashboard.i18n.test.tsx
git rm scada-reporter/frontend/src/pages/Metrics.tsx
git commit -m "feat(dashboard): merge Live Metrics into Dashboard System+Database tabs"
```

---

### Task 5: Manual verification

**Files:** none (runtime check).

- [ ] **Step 1: Start the app and verify the merged page**

Run: `just dev` (or `just run-frontend` if backend already up).

Verify in the browser:
- Dashboard tab bar shows 5 tabs: Overview, Watchlist, Tags, System, Database.
- **System** tab: poller stat cards, deadband savings card, PLC read-latency table, live console streaming.
- **Database** tab: DB stat cards + per-table rows; "Yenile" button refetches.
- Sidebar no longer shows "Canlı Metrikler".
- Navigating to `/metrics` redirects to `/` (Overview tab).
- Switching away from System stops the 2s poll / SSE (verify in Network tab: requests stop when not on System).

- [ ] **Step 2: Commit (only if any fix was needed)**

```bash
git add -A
git commit -m "fix(dashboard): metrics merge verification fixes"
```

---

## Self-Review

**Spec coverage:**
- 5-tab structure (Overview/Watchlist/Tags/System/Database) → Task 4 Step 4. ✓
- System tab content (poller, deadband, latency, console) → Task 2. ✓
- Database tab content (size/total/earliest/tags, day/week/month, growth, tables, refresh) → Task 3. ✓
- Shared `StatCard`/`fmtMs`/`fmtPct` in `metricsShared.tsx` → Task 1. ✓
- `active`-gated polling (metrics 2s, deadband 10s, SSE, DB manual) → Task 2 (queries + console), Task 3 (DB). ✓
- `/metrics` → redirect to `/` → Task 4 Step 6. ✓
- Drop sidebar item → Task 4 Step 7. ✓
- Delete `Metrics.tsx` → Task 4 Step 8. ✓
- i18n `tab_system`/`tab_database` in 5 locales → Task 4 Step 1. ✓
- Tests (console retarget, DB tab, Dashboard tabs, route) → Tasks 2/3/4. ✓
- Out of scope (URL tab state, backend changes, restyle) → not present. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Full code in every code step. ✓

**Type consistency:** `SystemTab`/`DatabaseTab` both `({ active }: { active: boolean })`. `StatCard`/`fmtMs`/`fmtPct` signatures match between `metricsShared.tsx` (Task 1) and consumers (Tasks 2/3). Query keys `['metrics']`, `['deadbandSavings']`, `['database-stats']` preserved from the original page. ✓
