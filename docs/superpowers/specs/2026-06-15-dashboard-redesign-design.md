# Design: Dashboard Redesign — Filtering & Tabbed Listing

**Date:** 2026-06-15
**Status:** Approved (design)
**Topic:** Make the dashboard usable with 3000+ tags via a tabbed, filtered, per-user layout.

---

## 1. Problem / Context

After importing the archive catalog, the dashboard lists **3,027 tags in a single page**,
grouped by device, refetching every current value every 5 s. This is unusable: huge DOM,
heavy server query, slow browser. Tags have **no units** (WinCC export omitted them) and
structured names (`B110<area><equipment><n>.<measurement>`). There are 27 PLCs/devices.

Goal: a usable dashboard with summary, a per-user watchlist of key tags, and a filtered,
paginated view of all tags. Real-time, but only for what is on screen.

## 2. Decisions (from brainstorming)

- **Layout:** tabbed — `Özet` / `İzleme Listesi` / `Tüm Tag'ler`. Only the active tab fetches data.
- **Watchlist:** per-user, stored in the backend DB (multi-user, survives device change).
- **Filters (Tüm Tag'ler):** PLC/device, name search, quality, daily-tracking.
- **Scope:** only `long_term` (archive) tags are shown/polled (already enforced in poller/overview).

## 3. Tabs

### 3.1 Özet (Summary)
- **KPI cards:** Aktif Tag (count), Son 24 Saat Okuma, Son Veri (timestamp), PLC Bağlı (`x/y`).
- **PLC status table:** one row per PLC with a connected/disconnected dot, from `/health.plcs`
  (surfaces the unreachable PLCs at a glance).
- Data: `GET /api/dashboard/overview` (10 s) + `GET /health` (10 s).

### 3.2 İzleme Listesi (Watchlist)
- Lists the current user's pinned tags with live value, refreshed every 5 s.
- Each row: device, name, value, time, quality dot, unpin (★) button.
- Small set → cheap query.
- Data: `GET /api/dashboard/watchlist` (5 s).

### 3.3 Tüm Tag'ler (All tags)
- **Filter bar:** PLC/device dropdown (27) · name search (debounced) · quality select
  (İyi / Hatalı / Bayat / Hepsi) · daily-tracking toggle.
- **Paginated table** (50/page): name · PLC · value · time · quality dot · pin (★) toggle.
- Only the visible page (≤50 rows) refreshes every 5 s → 50 latest-value lookups, not 3027.
- Data: `GET /api/dashboard/tags?...` (5 s, keyed by filters+page).

## 4. Backend

### 4.1 New model + migration
`Watchlist` table:
- `id` PK, `user_id` FK→users, `tag_id` FK→tags, `created_at`
- unique constraint `(user_id, tag_id)`
- Alembic revision `down_revision = a1b2c3d4e5f6` (current head). Additive `create_table` —
  works on SQLite + Postgres.

### 4.2 Endpoints (in `app/api/dashboard.py`)
- `GET /dashboard/watchlist` → current user's watchlist tags + latest reading
  `[{tag_id, name, device, unit, value, timestamp, quality_ok}]`.
- `POST /dashboard/watchlist/{tag_id}` → add (idempotent; 201/200). Requires auth user.
- `DELETE /dashboard/watchlist/{tag_id}` → remove (204).
- `GET /dashboard/tags` → filtered, paginated list with latest value:
  - query params: `device` (optional), `search` (optional, ILIKE on name), `quality`
    (`good`|`bad`|`stale`|omitted), `daily` (bool), `page` (default 1), `page_size` (default 50, max 200).
  - response: `{items: [{tag_id, name, device, value, timestamp, quality_ok}], total, page, page_size, total_pages}`.
  - **Query strategy:** filter `Tag` rows (is_active, long_term, + filters) → count + paginate
    the tag rows first; then fetch latest `TagReading` only for that page's tag_ids (≤page_size).
    Avoids scanning latest-of-all-3027 every request.
  - **quality filter semantics** computed from the latest reading: `good` = quality 192;
    `bad` = quality ≠ 192; `stale` = latest timestamp older than `3 × sample_interval`
    (or no reading). Applied after the latest-reading fetch for the page.
- **Remove** the existing heavy `GET /dashboard/current-values` (all 3027) — replaced by the above.
- `GET /dashboard/overview` stays (already `long_term`-filtered).

### 4.3 Auth
Watchlist endpoints use the existing `get_current_user` dependency to scope by `user.id`.

## 5. Frontend

- `pages/Dashboard.tsx` — tab container, `activeTab` state, renders one tab component.
- `pages/dashboard/OverviewTab.tsx` — KPI cards + PLC status table.
- `pages/dashboard/WatchlistTab.tsx` — pinned tags, live, unpin.
- `pages/dashboard/AllTagsTab.tsx` — filter bar + paginated table + pin toggle.
- `api/client.ts` — new types + functions: `getWatchlist`, `addWatchlist`, `removeWatchlist`,
  `getDashboardTags(params)`; remove `getCurrentValues`/`CurrentValue` (or repurpose).
- **Polling:** TanStack Query with `enabled: activeTab === '<tab>'` so inactive tabs don't fetch.
  Watchlist & AllTags `refetchInterval: 5000`; Overview/health `10000`.
- Pin (★) mutation invalidates `['watchlist']` and the current `['dashboard-tags', filters]` query.

## 6. Performance notes
- Active-tab-only fetching + page-only polling caps live work at ≤50 rows + the watchlist set.
- Server filters/paginates tag rows before any reading lookup.
- DOM never renders more than one page (50) + the watchlist.

## 7. Out of scope
- Units (data not available; tag edit can add them later).
- Alarms (removed earlier).
- Charts/trends (separate Trend page already exists).
- Virtualized infinite scroll (pagination is enough at 50/page).

## 8. Testing / verification
- Backend pytest: watchlist add/remove/list (per-user isolation); `/dashboard/tags` filtering
  (device, search, quality good/bad/stale, daily) + pagination (total/total_pages, page bounds).
- Migration round-trip on SQLite.
- Frontend `tsc --noEmit` clean.
- Manual: open dashboard, switch tabs, filter by PLC, search, pin/unpin, confirm only the
  active tab/page polls (network tab).
