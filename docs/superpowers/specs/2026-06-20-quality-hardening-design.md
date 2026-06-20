# Quality & Hardening Improvements — Design Spec

**Date:** 2026-06-20
**Status:** Approved, ready for implementation plan
**Scope:** Test/CI integrity, RTL completeness, i18n lint coverage, dev DX, DB performance, metric accuracy, timezone correctness, optional E2E-in-CI. No new user-facing features.

## Goal

Close a set of quality gaps surfaced while shipping the Arabic/RTL + rebrand work. None of these change product behaviour for end users; together they stop silent breakage (untested CLI, locale leaks), finish the RTL feature properly, and remove sharp edges in the dev loop. Each item is independently shippable.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CLI test fix approach | Align tests to the real `get_client` seam | Production code is correct; the tests mock a seam (`get_token`/`ScadaClient`) those modules never import. Fix the tests, not the code. |
| agent-harness in CI | Add a third CI job | 15 CLI tests are red and invisible because CI only runs `backend/tests` and `frontend`. A green CI must mean the CLI works too. |
| RTL physical→logical | Convert directional utilities in page bodies | `dir="rtl"` only mirrors correctly if spacing/alignment use logical (`ms-`/`ps-`/`text-start`) not physical (`ml-`/`pl-`/`text-left`) classes. |
| i18n guard scope | Add a JSX literal-text check alongside the Turkish-char check | Current guard only catches Turkish characters, so hardcoded **English** UI text passes silently. |
| Deadband window | Per-tag effective span | The global span approximation over-/under-counts when tags start at different times; per-tag is exact and we already group per tag. |
| Timestamps | Standardize on timezone-aware UTC end-to-end | Naive-UTC + frontend `+ 'Z'` works today but is fragile and easy to regress. |
| E2E in CI | Optional / gated job | Real value but needs a running backend + seeded data; keep it a separate, non-blocking job so it can't flake the required checks. |

## Background (verified this session)

- `/api/dashboard/overview` was slow (~10 s, occasionally minutes under poller write-lock) because `tag_readings` (11M rows) had no standalone `timestamp` index; the composite PK `(tag_id, timestamp)` can't serve `max(timestamp)` / time-window counts. Fixed via `ix_tag_readings_timestamp` (migration `a7c2e9f04b18`). This spec extends that index audit to the other hot paths.
- Deadband savings showed a misleading 99.9 %; fixed to use an *effective* window (first→last reading in the window) — but currently a **global** span, applied to every tag.
- The agent-harness suite has 15 failures, confirmed pre-existing (stash-verified), all from `explore`/`reports` tests mocking the wrong seam.

---

## Architecture

### 1. Agent-harness test integrity + CI coverage

**Current state.** `commands/explore.py` and `commands/reports.py` obtain their HTTP client via `from scada_reporter_cli.utils.client_helper import get_client` and call `get_client(...)`. The tests, however, patch `scada_reporter_cli.commands.<mod>.get_token` and `.ScadaClient` — names those modules never import — so `unittest.mock.patch` raises `AttributeError: module ... does not have the attribute 'get_token'`. `tags`/`dashboard` tests pass because those modules *do* import `get_token`/`ScadaClient` directly.

**Design.**
- Repoint the failing `explore`/`reports` tests at the real seam: `patch("scada_reporter_cli.commands.explore.get_client", return_value=mock_client)` (and the `reports` equivalent), shaping `mock_client` to the methods each command calls.
- Where a test needs the "no token → friendly error" path, patch `get_client` to raise / return the same not-authenticated signal the command handles.
- Record the seam convention in `agent-harness/TEST.md` so future command tests mock `get_client`, not internal token plumbing. (Reinforces knowledge-base entry `[150626]`.)
- **CI:** add a `cli` job to `.github/workflows/ci.yml` mirroring the backend job: set up `uv`, install the backend venv + the harness (`uv pip install -e ../agent-harness` or equivalent), run `pytest tests/ -v` from `scada-reporter/agent-harness`. It becomes a required check on push/PR to `master`.

**Acceptance.** `pytest tests/` in `agent-harness` is green; CI runs and gates on it.

### 2. RTL completeness — physical → logical utilities

**Current state.** Arabic sets `<html dir="rtl">`, but page bodies still use physical Tailwind utilities. Counts of files containing `text-left|text-right|ml-|mr-|pl-|pr-|left-|right-`: Trend 12, AdvancedReports 9, Tags 7, Metrics 5, OverviewTab 4, PlcConfig 4, others ≤3.

**Design.**
- Convert **directional flow** utilities to logical: `ml-*→ms-*`, `mr-*→me-*`, `pl-*→ps-*`, `pr-*→pe-*`, `text-left→text-start`, `text-right→text-end`, `rounded-l/​r→rounded-s/e`, `border-l/r→border-s/e`.
- **Do not** blindly convert `left-*`/`right-*` used for *absolute positioning of visually-fixed chrome* (e.g. a close "×" that should stay top-right regardless of direction) — review each; many `left-`/`right-` hits are positioning, not flow.
- Recharts/SVG axis orientation and chart internals stay LTR (numeric axes); only the surrounding DOM mirrors. Document this boundary.
- Add a lightweight regression note (and optionally an ESLint/grep guard) discouraging new `text-left`/`ml-`/`pl-` in `src/pages` and `src/components`.

**Acceptance.** Each page reviewed under `dir="rtl"`; spacing/alignment mirror correctly; LTR locales visually unchanged. Spot-checked in-browser (Playwright/puppeteer-core) for Trend, Tags, AdvancedReports.

### 3. i18n guard — catch untranslated English too

**Current state.** `scripts/check-hardcoded-strings.mjs` flags only Turkish characters (`/[şğıçöüŞĞİÇÖÜ]/`). A component with hardcoded **English** UI text (the ExcelTemplates case, had it been authored in English) passes silently.

**Design.**
- Extend the guard with a second, conservative pass that flags **literal text in JSX children and common string-bearing attributes** (`title`, `placeholder`, `aria-label`, `alt`) that isn't wrapped in `t(...)`.
- Keep false positives low: ignore strings with no letters (icons, numbers, symbols), single-token technical identifiers, `className`/`type`/`key`/`d` (SVG path) attributes, units, and an explicit per-file/regex allowlist (`LanguageSelector` native names, etc.).
- Run as a non-zero-exit lint step (already wired into `pnpm lint`). Phase it in: first as a **warning list** to triage existing debt, then flip to failing once the backlog is zero.

**Acceptance.** The guard flags a newly-added hardcoded English `<p>Hello</p>` in a page; existing translated pages pass; `pnpm lint` stays green after the backlog is cleared.

### 4. Dev DX — reliable backend reload

**Current state.** `uvicorn --reload` on this Windows host frequently fails to pick up `.py` edits (watchfiles logs "change detected" but the app isn't re-served), forcing a full `Get-Process python | Stop-Process` + restart. The SQLite dev DB lives inside the watched tree and its WAL/SHM churn adds noise.

**Design.**
- Constrain the reloader: `--reload-dir app` (watch only `app/`), and exclude the DB artifacts (`--reload-exclude "*.db" --reload-exclude "*.db-wal" --reload-exclude "*.db-shm"`), wired into the `just run-backend` recipe.
- If watchfiles remains unreliable, document the deterministic restart (`just restart-backend` recipe that kills python and relaunches) as the supported workflow and note it in `CLAUDE.md`/`TOOL.md`.

**Acceptance.** Editing a handler is reflected without a manual kill, **or** a one-command restart recipe exists and is documented.

### 5. DB performance — index audit of remaining hot paths

**Current state.** Only `tag_readings.timestamp` was added. Other time-windowed reads (trend, continuous-aggregate fallbacks, watchlist latest-value, deadband counts) may still scan.

**Design.**
- Run `EXPLAIN QUERY PLAN` against the queries behind `/dashboard/trend`, `/dashboard/trend_range`, `/dashboard/trend_agg`, `/dashboard/watchlist` (latest-per-tag subquery), and `/dashboard/deadband_savings`.
- For any `SCAN tag_readings` without a usable index, add the minimal covering index (e.g. confirm `(tag_id, timestamp)` PK is exploited for tag-scoped ranges; add composite/partial indexes only where a plan shows a full scan). Ship as Alembic migration(s).
- Capture before/after timings in the migration docstring (as done for `a7c2e9f04b18`).

**Acceptance.** No `/dashboard/*` read shows a full `tag_readings` scan in its query plan; representative queries are sub-100 ms on the 11M-row dev DB.

**Audit result (2026-06-20).** `EXPLAIN QUERY PLAN` + timings on the 11M-row dev DB confirm **no new index is needed** — the existing schema already serves every hot path:

| Query | Plan | Time |
|-------|------|------|
| overview `max(timestamp)` | COVERING `ix_tag_readings_timestamp` | 0.2 ms |
| overview `count` 24 h | COVERING `ix_tag_readings_timestamp` (range) | 59 ms |
| overview `count` + `quality` 1 h | `ix_tag_readings_timestamp` (range) + row filter | 0.1 ms |
| deadband `min/max` 24 h | COVERING `ix_tag_readings_timestamp` (range) | 109 ms |
| deadband per-tag join | SCAN `tags` (3 027 rows) + PK `(tag_id, timestamp)` | 125 ms |
| watchlist latest-per-tag | COVERING PK `(tag_id=?)` | 24 ms |
| trend (5 busiest, 24 h) | PK `(tag_id=? AND timestamp≥?)` + temp-btree sort | 52 ms |

The only `SCAN` is over the small `tags` table (3 027 rows) in the deadband aggregation — expected and cheap; its filters (`is_active`/`long_term`/`deadband>0`) aren't selective enough to index. `tag_readings` is never fully scanned; tag-scoped ranges use the PK, time-windowed reads use `ix_tag_readings_timestamp`. The remaining costs (counting/min-max over a bounded range, trend's merge-sort across tags) are query-shape inherent and not addressable by an index. The prior `a7c2e9f04b18` migration closed the real gap; this audit ships no migration.

### 6. Deadband metric — per-tag effective span

**Current state.** `deadband_savings` computes one **global** effective window (`min(window, last_ts − first_ts)` across all readings) and applies it to every deadband tag's expected-row count. A tag that started collecting later than the global `first_ts` gets its expected rows overstated.

**Design.**
- Extend the existing per-tag aggregation query (already `GROUP BY Tag.id`) to also select `min(timestamp)`/`max(timestamp)` per tag.
- Compute each tag's expected rows over its **own** span `min(window_seconds, last_i − first_i)` ÷ `sample_interval`; sum for the totals.
- Keep the response shape; `effective_seconds` becomes the max per-tag span (or drop it in favour of a per-tag-derived total) — decide during implementation and update `test_deadband_savings.py` accordingly.

**Acceptance.** Unit test: two tags with different spans produce expected rows summed per-tag, not from a single global span. Endpoint test updated.

### 7. Timezone-aware timestamps end-to-end

**Current state.** Readings are stored as **naive** UTC (`datetime.now(UTC)` written without tzinfo by SQLite); the frontend reconstructs UTC by appending `'Z'` (`parseISO(last_reading + 'Z')`). Correct today, but every new timestamp consumer must remember the `+ 'Z'` trick.

**Design.**
- Backend: ensure datetimes are serialized with an explicit UTC offset (model/serializer returns ISO‑8601 with `Z`/`+00:00`), so clients don't guess.
- Frontend: drop the manual `+ 'Z'` once the API is offset-aware; centralize parsing in one helper.
- This is a careful, test-guarded change (trend ranges, report periods, "last data" card all touch timestamps); land it behind its own tests.

**Acceptance.** API timestamps carry an explicit offset; frontend renders identical local times without string hacks; trend/report/last-data tests pass.

### 8. (Optional) E2E in CI

**Current state.** Playwright (`pnpm e2e`) + puppeteer-core (`pnpm e2e:verify`) exist locally; nothing runs them in CI.

**Design.**
- Add a **non-blocking** `e2e` job: boot the backend (SQLite + a small seeded dataset, or `seed-users` + a handful of tags), `pnpm build`/preview the frontend, run `pnpm e2e` (chromium) headless.
- Keep it `continue-on-error` / not a required check initially to avoid flaking the gate; promote to required once stable.

**Acceptance.** The dashboard smoke spec runs in CI against a booted stack; failures are visible but don't block merges until promoted.

## Build order

1. **#1 CLI tests + CI job** — stops silent breakage; smallest, highest signal.
2. **#5 index audit** — quick wins, pure migrations, no API change.
3. **#6 deadband per-tag** — localized backend change with existing tests.
4. **#2 RTL physical→logical** — finishes the RTL feature; page-by-page.
5. **#3 i18n guard** — prevents future locale leaks (warning→failing).
6. **#4 reload DX** — tooling/justfile + docs.
7. **#7 timezone** — most cross-cutting; do last, behind tests.
8. **#8 E2E in CI** — optional, after the rest is green.

## Out of scope

- Renaming the `scada-reporter/` directory, `scada_reporter_cli` package, or `scada_reporter.db` (would break paths/imports/CI; intentionally untouched in the rebrand too).
- New product features, new pages, or visual redesigns.
- API error/validation message i18n (still English by prior decision).
- Pixel-mirroring chart internals for RTL (numeric axes stay LTR).
- Production deployment / Docker changes.
