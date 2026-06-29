# Dashboard + Live Metrics Merge

**Date:** 2026-06-29
**Status:** Approved design
**Scope:** Frontend only. No backend/API changes.

## Goal

Fold the standalone `/metrics` page ("Canlı Metrikler") into the Dashboard page
as two new tabs. The Dashboard already uses a local-state tab bar (Overview /
Watchlist / Tags); this follows the same pattern as the recently shipped
PlcConfig + PlcHealth → Plc merge.

Final Dashboard tab bar:

```
[ Overview ][ Watchlist ][ Tags ][ System ][ Database ]
```

- **System** — poller metrics stat cards, deadband (report-by-exception)
  savings card, PLC read-latency table, live log console.
- **Database** — DB size / total readings / earliest / tag count, last
  day/week/month counts, estimated monthly growth, per-table row counts, and
  the manual "Yenile" refresh button.

## Current state

- `pages/Dashboard.tsx` — tabbed page (`useState<Tab>`), renders
  `OverviewTab` / `WatchlistTab` / `AllTagsTab` from `pages/dashboard/`. Each
  tab receives an `active` prop. Header shows title + WS "Live" status badge
  (`useLiveDashboard`).
- `pages/Metrics.tsx` — single long-scroll page. Contains local `StatCard`,
  `fmtMs`, `fmtPct`, `LiveConsole` (SSE via `useLogStream`), the metrics
  query (`getMetrics`, 2s poll), deadband query (`getDeadbandSavings`, 10s
  poll), and DB stats query (`getDatabaseStats`, manual refetch).
- `App.tsx` — route `/metrics` → `<Metrics />`.
- `components/Layout.tsx` — sidebar item `{ to: '/metrics', labelKey: 'nav_metrics' }`.
- i18n: section strings live in the `metrics` namespace; tab labels in the
  `dashboard` namespace.

## Target structure

Mirror the existing `pages/dashboard/` tab convention.

### New files

- `pages/dashboard/SystemTab.tsx`
  - Props: `{ active: boolean }`.
  - Contains the poller stat cards, deadband savings card, PLC read-latency
    table, and `LiveConsole`.
  - Owns the `metrics` query and `deadbandSavings` query, both gated
    `enabled: active`.
  - `LiveConsole` moves here (or to a shared file — see below). Its
    `useLogStream` is gated so the SSE stream is requested only when the tab
    is active.
- `pages/dashboard/DatabaseTab.tsx`
  - Props: `{ active: boolean }`.
  - Contains the `database-stats` query (manual refetch, unchanged) + the
    "Yenile" refresh button and all DB stat cards / table list.
  - Uses `formatBytes` from `pages/metricsDb.helper.ts` (unchanged).

### Shared helpers

`StatCard`, `fmtMs`, `fmtPct` are used by SystemTab (and `StatCard` by
DatabaseTab). Extract them to `pages/dashboard/metricsShared.tsx` so both tabs
import the same component. Keep it tiny — presentational only.

### Modified files

- `pages/Dashboard.tsx`
  - Add `'system'` and `'database'` to the `Tab` union and `TABS` array
    (`labelKey: 'tab_system'` / `'tab_database'`).
  - Render `<SystemTab active={activeTab === 'system'} />` and
    `<DatabaseTab active={activeTab === 'database'} />`.
  - Header WS "Live" badge unchanged (it reflects the Overview live stream).
- `App.tsx`
  - Replace `import Metrics` route with a redirect:
    `<Route path="metrics" element={<Navigate to="/" replace />} />`.
  - Remove the `import Metrics from './pages/Metrics'` line.
- `components/Layout.tsx`
  - Remove the `{ to: '/metrics', labelKey: 'nav_metrics' }` nav entry.

### Deleted files

- `pages/Metrics.tsx` — fully replaced by the two tabs + shared helper.

## Polling lifecycle (improvement)

On the standalone page the metrics (2s) and deadband (10s) queries and the SSE
log stream ran continuously while mounted. Inside the tabbed Dashboard, gate
them on `active` so they do not poll/stream while the user is on another tab:

- `metrics` query: `enabled: active`, `refetchInterval: active ? 2000 : false`.
- `deadbandSavings` query: `enabled: active`, `refetchInterval: active ? 10000 : false`.
- `LiveConsole` `useLogStream(level, active && !paused)` — stream only when the
  System tab is active and not paused.
- Database tab query stays manual (`refetchInterval: false`); it also fetches
  on first activation only (`enabled: active`).

This avoids hidden background polling that the separate-page layout did not
have to worry about.

## Routing / nav behavior

- Sidebar "Canlı Metrikler" item removed.
- `/metrics` redirects to `/` (preserves old bookmarks/links, same approach as
  `plc-health` → `plc`). It lands on the default **Overview** tab — tab state
  is local `useState`, not in the URL. Deep-linking to a specific tab is out of
  scope.

## i18n

- Add `tab_system` and `tab_database` to the `dashboard` namespace for all five
  locales (en / tr / ru / de / ar).
  - Suggested tr: `tab_system` = "Sistem", `tab_database` = "Veritabanı".
  - Suggested en: "System" / "Database".
- All section strings remain in the `metrics` namespace; SystemTab and
  DatabaseTab keep `useTranslation(['metrics', 'common'])`.
- `nav_metrics` key may be left in locale files (unused, harmless) or removed;
  removing is cleaner. Tests should not assert its presence in the sidebar.

## Tests

- `pages/Metrics.console.test.tsx` → retarget to `SystemTab` (console
  pause/clear/filter behavior). Move under `pages/dashboard/` if convenient.
- `pages/metricsDb.helper.test.ts` — unchanged.
- New `pages/dashboard/Dashboard.tabs.test.tsx` (or extend the existing
  `pages/dashboard/Dashboard.i18n.test.tsx`): assert all five tab labels render
  and that clicking System/Database swaps content.
- Any route test referencing `/metrics` (e.g. `Users.route.test.tsx` if it
  enumerates routes) → assert `/metrics` redirects to `/`.
- Run the existing frontend suite (`pnpm test` / vitest) — expect green.

## Risk

Low. Pure frontend reshuffle. The backend endpoints
(`getMetrics` / `getDeadbandSavings` / `getDatabaseStats` and the log SSE
stream) and their API client are untouched. The only behavioral change beyond
relocation is the `active`-gated polling, which strictly reduces background
work.

## Out of scope

- URL-driven tab state / deep-linking to a tab.
- Any change to the metrics/DB-stats/deadband backend endpoints.
- Restyling the metrics sections (they move verbatim).
