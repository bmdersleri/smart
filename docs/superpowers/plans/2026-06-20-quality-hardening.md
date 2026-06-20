# Quality & Hardening Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight quality gaps in `2026-06-20-quality-hardening-design.md`: CLI test integrity + CI coverage, RTL physical→logical utilities, an i18n guard that also catches English, reliable backend reload, a DB index audit, per-tag deadband spans, timezone-aware timestamps, and an optional E2E-in-CI job.

**Architecture:** Each task is independent and shippable on its own branch. Backend changes are TDD (failing test → implement → green). Frontend RTL/i18n changes are verified with `tsc` + `vitest` + `pnpm lint` and spot-checked in a real browser via the existing E2E tooling.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (backend, Python 3.14 venv); Click + pytest (agent-harness); React 19 + Vite + Tailwind v4 + react-i18next + Vitest + Playwright (frontend); GitHub Actions (CI).

## Global Constraints

- Backend tests run from `scada-reporter/backend`: `.venv/Scripts/pytest tests/ -q`. SQLite dev DB; alembic targets it via `DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db .venv/Scripts/python -m alembic ...`.
- Agent-harness tests run from `scada-reporter/agent-harness`: `../backend/.venv/Scripts/pytest tests/ -q`.
- Frontend from `scada-reporter/frontend`: `pnpm test`, `node_modules/.bin/tsc --noEmit`, `pnpm lint`, `pnpm e2e` (chromium installed) / `pnpm e2e:verify` (system Chrome). Backend must be on :8001 with data for E2E.
- **Do NOT run `prettier --write`** on the frontend (project uses compact one-line style; prettier reformats whole files). Manual compact edits + `tsc`/`eslint` only.
- Migrations: model change → `just makemigration` (or hand-author chained from current head) → run + verify upgrade/downgrade on the dev DB.
- One branch per task, fast-forward merge to `master`, push, delete branch. Verify before shipping (tests/lint green; browser-verify RTL).
- Do not rename `scada-reporter/`, `scada_reporter_cli`, or `scada_reporter.db`.

---

### Task 1: Fix agent-harness CLI tests + add CI job

**Files:**
- Modify: `scada-reporter/agent-harness/tests/test_cli.py` (repoint `explore`/`reports` patches to `get_client`)
- Modify: `scada-reporter/agent-harness/TEST.md` (document the `get_client` mocking convention)
- Modify: `.github/workflows/ci.yml` (add `cli` job)

**Interfaces:**
- `commands/explore.py` / `commands/reports.py` acquire their client via `get_client(...)` from `utils.client_helper`. Tests must patch `scada_reporter_cli.commands.<mod>.get_client`, shaping the mock to the methods the command calls.

- [ ] **Step 1: Reproduce** — `cd scada-reporter/agent-harness && ../backend/.venv/Scripts/pytest tests/ -q`. Confirm the 15 failures are `AttributeError: module 'scada_reporter_cli.commands.explore'|'.reports' does not have the attribute 'get_token'` / `'ScadaClient'`.
- [ ] **Step 2: Inspect the real seam** — read `commands/explore.py`, `commands/reports.py`, and `utils/client_helper.py:get_client` to learn the return type/methods (`get_client` likely returns a configured `ScadaClient` or raises when unauthenticated).
- [ ] **Step 3: Repoint the explore tests** — in `test_cli.py`, change every `patch("scada_reporter_cli.commands.explore.get_token", ...)` + `patch("...explore.ScadaClient", ...)` pair to a single `patch("scada_reporter_cli.commands.explore.get_client", return_value=mock_client)`. Build `mock_client` to return the fixtures the assertions expect (tags grouped by device, alarm info, JSON).
- [ ] **Step 4: Repoint the reports tests** — same change for the failing `reports` test(s) (`test_reports_download_history_saves_file` et al.): patch `scada_reporter_cli.commands.reports.get_client`.
- [ ] **Step 5: No-token path** — for tests asserting the friendly "not authenticated" error, make `get_client` raise the same exception the command catches (or return the sentinel it checks).
- [ ] **Step 6: Green** — `../backend/.venv/Scripts/pytest tests/ -q` → all pass (was 19 passed / 15 failed).
- [ ] **Step 7: Document** — in `TEST.md`, add: "Command tests mock `commands.<mod>.get_client` (the client seam), never internal `get_token`/`ScadaClient`."
- [ ] **Step 8: CI job** — add to `ci.yml` a `cli` job (ubuntu, `working-directory: scada-reporter/agent-harness`): setup-uv (python 3.12), create backend venv + `uv pip install -e ../agent-harness` (and its deps), then `uv run --no-sync pytest tests/ -v --tb=short`. Mirror the backend job's structure.
- [ ] **Step 9: Verify CI locally as far as possible** — re-run the harness tests; push the branch and confirm the new job goes green in Actions.

---

### Task 2: DB index audit for remaining hot paths

**Files:**
- Read: `backend/app/api/dashboard.py` (trend, trend_range, trend_agg, watchlist, deadband_savings queries)
- Add: `backend/alembic/versions/<rev>_hotpath_indexes.py` (only if a plan shows a full scan)
- Modify (if needed): `backend/app/models/tag.py` / others (`index=True` to keep model ↔ schema in sync)

**Interfaces:** New indexes are additive; no API shape change.

- [ ] **Step 1: Capture plans** — for each query, run `EXPLAIN QUERY PLAN <sql>` against `scada_reporter.db` (reuse the inline-python pattern). Record which show `SCAN tag_readings`.
- [ ] **Step 2: Decide indexes** — for each full scan, design the minimal index. Confirm the `(tag_id, timestamp)` PK already serves tag-scoped range scans (likely no new index for trend-by-tag). Add composite/partial indexes only where justified.
- [ ] **Step 3: Migration** — hand-author a migration chained from the current head; `op.create_index(...)`. Mirror with `index=True` on the model column(s) so `create_all` matches.
- [ ] **Step 4: Verify** — `alembic upgrade head` on the dev DB; re-run `EXPLAIN QUERY PLAN` → indexes used, no full scan; time representative queries (<100 ms). Record before/after in the migration docstring.
- [ ] **Step 5: Downgrade** — verify `alembic downgrade -1` drops cleanly.
- [ ] **Step 6: Tests** — `pytest tests/` green (existing dashboard/trend tests exercise these paths).

---

### Task 3: Deadband metric — per-tag effective span

**Files:**
- Modify: `backend/app/api/dashboard.py` (`deadband_savings` endpoint + `compute_deadband_savings`)
- Modify: `backend/tests/test_deadband_savings.py`

**Interfaces:** `GET /dashboard/deadband_savings?hours=N` keeps its response keys; expected rows now derive from per-tag spans.

- [ ] **Step 1: Failing test** — add a unit test: two items with different per-tag spans (e.g. tag A spans 9 min, tag B spans 3 min in a 1 h window) must yield expected rows = `spanA//si + spanB//si`, not from one global span. Assert the new totals.
- [ ] **Step 2: Verify it fails** against the current global-span implementation.
- [ ] **Step 3: Extend the query** — add `func.min(TagReading.timestamp)`, `func.max(TagReading.timestamp)` to the existing per-tag `GROUP BY Tag.id` aggregation; carry each tag's span into `items`.
- [ ] **Step 4: Per-tag compute** — change `compute_deadband_savings` to take per-item `effective_seconds` (or compute expected = `min(window, span_i)//si` per item). Update `saved_rows_per_day` extrapolation accordingly; keep response keys (`effective_seconds` = max/representative span, or document the change).
- [ ] **Step 5: Update endpoint test** — adjust `test_endpoint_only_counts_deadband_tags` expectations to per-tag math.
- [ ] **Step 6: Green** — `pytest tests/test_deadband_savings.py -q`; live-check `/dashboard/deadband_savings` returns a sane %.

---

### Task 4: RTL physical → logical utilities

**Files:**
- Modify: `frontend/src/pages/{Trend,AdvancedReports,Tags,Metrics,PlcConfig,Reports,Users}.tsx`, `pages/dashboard/{OverviewTab,AllTagsTab,WatchlistTab}.tsx`, and any `components/*` with directional flow classes.

**Interfaces:** No prop/API change; LTR locales must stay pixel-identical.

- [ ] **Step 1: Inventory** — `rg -n "text-left|text-right|\bml-|\bmr-|\bpl-|\bpr-|rounded-l|rounded-r|border-l|border-r" src/pages src/components`.
- [ ] **Step 2: Classify each hit** — *flow* (alignment/spacing → convert) vs *absolute-positioned chrome* (`left-`/`right-` for a fixed corner element → leave, or guard with `rtl:` if it should mirror).
- [ ] **Step 3: Convert flow utilities** — `ml→ms`, `mr→me`, `pl→ps`, `pr→pe`, `text-left→text-start`, `text-right→text-end`, `rounded-l/r→rounded-s/e`, `border-l/r→border-s/e`. Compact manual edits only (no prettier).
- [ ] **Step 4: tsc + lint + vitest** — `node_modules/.bin/tsc --noEmit`, `pnpm lint`, `pnpm test` all green.
- [ ] **Step 5: Browser-verify RTL** — with backend+frontend up, switch to `ar` and screenshot Trend, Tags, AdvancedReports via `pnpm e2e:verify` (or a small puppeteer script). Confirm alignment mirrors; spot-check an LTR locale is unchanged.
- [ ] **Step 6: Guard (optional)** — add a grep/eslint note flagging new `text-left|ml-|pl-` in `src/pages|src/components`.

---

### Task 5: i18n guard — catch untranslated English

**Files:**
- Modify: `frontend/scripts/check-hardcoded-strings.mjs`
- Add: `frontend/scripts/__tests__` fixture or a self-test (optional)

**Interfaces:** Runs in `pnpm lint`; non-zero exit on violation.

- [ ] **Step 1: Spec the matcher** — flag literal text in JSX children and in `title|placeholder|aria-label|alt` attributes that is letter-bearing and not inside `t(...)`. Ignore: numbers/symbols-only, `className|type|key|d|href|to|src`, single technical tokens, and an explicit allowlist (keep `LanguageSelector` native names).
- [ ] **Step 2: Implement as a second pass** — keep the existing Turkish-char pass; add the JSX-literal pass. Start in **warning mode** (print, exit 0) to enumerate existing debt.
- [ ] **Step 3: Triage backlog** — list what the new pass flags; wrap genuine UI strings in `t(...)` (new keys), allowlist legitimate literals.
- [ ] **Step 4: Flip to failing** — once the backlog is zero, make the new pass `exit 1` on violation.
- [ ] **Step 5: Prove it** — add a temporary `<p>Hello world</p>` to a page → guard fails; remove → passes. `pnpm lint` green.

---

### Task 6: Reliable backend reload (dev DX)

**Files:**
- Modify: `justfile` (`run-backend`, add `restart-backend`)
- Modify: `CLAUDE.md` / `TOOL.md` (document the workflow)

**Interfaces:** Dev-only; no app code change.

- [ ] **Step 1: Constrain the watcher** — change `run-backend` to `uvicorn app.main:app --reload --reload-dir app --reload-exclude "*.db" --reload-exclude "*.db-wal" --reload-exclude "*.db-shm" --host 0.0.0.0 --port 8001`.
- [ ] **Step 2: Test reload** — start it, edit a handler, confirm the change is served without a manual kill.
- [ ] **Step 3: Fallback recipe** — if reload is still unreliable, add `restart-backend` (PowerShell: `Get-Process python | Stop-Process -Force; just run-backend`) and document it as the supported path.
- [ ] **Step 4: Document** — note the chosen workflow in `CLAUDE.md` Notes and `TOOL.md`.

---

### Task 7: Timezone-aware timestamps end-to-end

**Files:**
- Modify: backend serializers/models that emit `TagReading.timestamp` (e.g. response models in `dashboard.py`, report builders) to ISO‑8601 with explicit UTC offset.
- Modify: `frontend/src` timestamp parsing (drop manual `+ 'Z'`; centralize in one helper, e.g. `src/utils/time.ts`).
- Modify: affected tests (backend trend/report; frontend OverviewTab/Trend).

**Interfaces:** API timestamps gain an explicit offset (`...Z`); frontend parses without string hacks. Behaviour (local-time rendering) unchanged.

- [ ] **Step 1: Failing tests** — backend: assert a representative timestamp field serializes with offset (`endswith('Z')` or `+00:00`). Frontend: a parse helper returns the correct instant from an offset-aware string.
- [ ] **Step 2: Backend** — make datetimes timezone-aware on the way out (UTC), without rewriting stored naive values (read-side normalization is acceptable).
- [ ] **Step 3: Frontend** — add `parseUtc()` helper; replace `parseISO(x + 'Z')` call sites; render identical local times.
- [ ] **Step 4: Regression** — run backend + frontend suites; browser-check the "Last Data" card and Trend axis show the same local times as before.
- [ ] **Step 5: Guard** — grep for any remaining `+ 'Z'` / naive parsing; remove or justify.

---

### Task 8 (optional): E2E in CI

**Files:**
- Modify: `.github/workflows/ci.yml` (add non-blocking `e2e` job)

**Interfaces:** Non-required check initially.

- [ ] **Step 1: Boot script** — in the job: create the backend venv, seed a minimal dataset (`seed-users` + a few tags, or a tiny SQLite fixture), start uvicorn on :8001 in the background.
- [ ] **Step 2: Frontend** — `pnpm install`, `pnpm build` + preview (or `pnpm dev`), `pnpm exec playwright install --with-deps chromium`.
- [ ] **Step 3: Run** — `pnpm e2e` (the dashboard smoke spec) headless; upload the HTML report as an artifact.
- [ ] **Step 4: Non-blocking** — mark `continue-on-error: true` (or a separate optional workflow) so flakes don't block merges.
- [ ] **Step 5: Promote (later)** — once stable across several runs, make it a required check.

---

## Suggested execution order

1, 2, 3 (backend/CLI, low-risk, high-signal) → 4, 5 (frontend RTL/i18n) → 6 (DX) → 7 (timezone, cross-cutting, last) → 8 (optional).

## Definition of done (per task)

- All relevant suites green (`backend pytest`, `agent-harness pytest`, `frontend tsc + lint + vitest`).
- Migrations upgrade **and** downgrade cleanly where applicable.
- RTL/timestamp changes spot-checked in a real browser.
- One commit (or a small, logical set), fast-forward merged to `master`, pushed, branch deleted.
