# EKONT SMART REPORT

Water/wastewater plant SCADA data acquisition and reporting system.

## Project Structure

```
scada-reporter/
├── backend/       # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/        # REST API (auth/dashboard/tags/reports/advanced_reports/plc/query/explore)
│   │   ├── collector/  # Snap7 S7 collector + built-in OPC UA server + poller
│   │   ├── core/       # Config, DB, security (JWT)
│   │   ├── models/     # Tag, User, PlcConfig, Watchlist, ReportHistory/Template/Scheduled/Archive
│   │   └── reports/    # Excel / PDF generators
│   ├── tests/          # pytest async tests (247+, parallel + randomized)
│   ├── alembic/        # DB migration files
│   ├── seed_users.py   # admin + operator user creation
│   ├── pyproject.toml  # pytest/ruff/mypy config
│   ├── .venv/          # Python venv (managed with uv, Python 3.14)
│   └── requirements.txt
├── frontend/      # React 19 + Vite + Tailwind CSS v4 + TanStack Query (:5173)
│   ├── src/
│   │   ├── pages/      # Dashboard, Trend, Reports, AdvancedReports, Tags, PlcConfig, Settings
│   │   ├── context/    # AuthContext, SettingsContext (localStorage)
│   │   └── api/        # Generated OpenAPI TypeScript client
│   ├── openapi-ts.config.ts  # TypeScript API client generator
│   └── package.json
├── agent-harness/ # Agent-native CLI (Click + JSON + REPL)
│   ├── src/scada_reporter_cli/
│   └── setup.py
├── commands/      # Claude Code slash commands (markdown)
├── guides/        # Agent methodology guides
├── .claude-plugin/  # Claude Code marketplace registration
└── AGENTS.md      # Agent usage guide
docker/        # TimescaleDB + Redis + Grafana
```

## Commands

### Development
- **Backend + Frontend in parallel:** `just dev`
- **Backend only:** `just run-backend` *(hot reload watches `app/` only)*
- **Restart backend (reload stuck):** `just restart-backend`
- **Frontend only:** `just run-frontend`
- **Install dependencies:** `just install`

### Test
- **Run tests:** `just test` *(247+ tests, parallel via pytest-xdist `-n auto`, randomized order via pytest-randomly)*
- **Coverage report:** `just test-cov`
- **TDD hot reload:** `just test-watch`
- **Serial run (debug):** `just test` then add `-n0` to disable parallelism, or `-p no:randomly` to fix order

### Database
- **Apply migration:** `just migrate`
- **Create migration:** `just makemigration msg="description"`
- **Roll back migration:** `just migrate-down`
- **Migration history:** `just migrate-history`
- **Add PLC tags:** `just seed-tags`
- **Default users:** `just seed-users` *(admin/admin123, operator/operator123)*
- **WinCC xlsx catalog:** `just seed-catalog`

### Quality
- **Lint:** `just lint`
- **Lint + auto-fix:** `just lint-fix`
- **Format:** `just format`
- **Type check:** `just typecheck`
- **All checks (CI):** `just check`

### Agent CLI
- **Install the CLI:** `just install-agent`
- **Test it:** `just test-agent`
- **REPL (interactive):** `just agent-repl`
- **SQL query:** `just agent cli_args="query run 'SELECT * FROM tags LIMIT 5' --json"`
- **Database discovery:** `just agent cli_args="explore schema"`
- **Python REPL:** `just agent cli_args="shell"`
- **Single command:** `just agent cli_args="tags list --json"`

### Tools
- **Generate TS API client:** `just gen-client` *(while backend running)*
- **PLC connection test:** `just test-plc`
- **Start/stop Docker:** `just docker-up` / `just docker-down`
- **License (vendor):** `just license "keygen --type rsa"` / `just license "issue ..."` *(generate keys / issue licenses — `scripts/generate_license.py`)*
- **Project tree:** `just tree`

## Database

- Dev/test: SQLite (`scada_reporter.db`) — no Docker required
- Prod: PostgreSQL (TimescaleDB) + Redis (via Docker)
- Copy `.env.example` → `.env` and set the env vars

## Available Tools

| Tool | Version | Usage |
|------|---------|-------|
| Python | 3.14.6 | `python` or `.venv\Scripts\activate` |
| uv | 0.11.21 | Fast pip alternative |
| ruff | 0.15.17 | Python linter + formatter |
| mypy | 2.1.0 | Python type checker |
| Node.js | 24.16.0 | JS runtime |
| pnpm | 11.6.0 | Fast npm alternative |
| TypeScript | 6.0.3 | `tsc` |
| Prettier | 3.8.4 | Code formatter |
| Git | 2.54.0 | Version control |
| Go | 1.26.4 | Go language |
| Rust | 1.96.0 | `rustc` + `cargo` |
| .NET SDK | 10.0.301 | Dotnet |
| ripgrep | 15.1.0 | Fast code search (`rg`) |
| fd | 10.4.2 | Fast file find |
| bat | 0.26.1 | View with syntax highlight |
| fzf | 0.73.1 | Fuzzy finder |
| jq | 1.8.1 | JSON processing |
| yq | 4.53.3 | YAML/JSON/XML processing |
| gh | 2.94.0 | GitHub CLI |
| lazygit | 0.62.2 | Terminal Git UI |
| delta | 0.19.2 | Git diff viewer |
| tldr | 0.6.1 | Short man pages |
| eza | 0.23.4 | Modern ls |
| zoxide | 0.9.9 | Smart cd (`z <dir>`) |
| btop | 1.0.5 | System monitor |
| dust | 1.2.4 | Disk usage analysis |
| hyperfine | 1.20.0 | Benchmark |
| just | 1.52.0 | Command runner |
| codegraph | 1.0.1 | Semantic code intelligence (`codegraph explore/node`) |

## Notes

- **Built-in OPC UA Server**: `opc.tcp://localhost:4840` — comes up automatically when the backend starts. No paid third-party software (KEPServerEX etc.) required.
- **S7 PLC connection**: direct to S7-1500 over TCP 102 via Snap7 (free, pure Python). Configured with the `S7_HOST`/`S7_RACK`/`S7_SLOT` env vars.
- **Simulation mode**: the backend runs fine when no PLC is present or reachable.
- **OAuth2 login**: `/api/auth/token` expects **form-data**, not JSON. The frontend sends it correctly; use `curl -d "username=...&password=..."`.
- **WeasyPrint PDF**: requires the GTK3 runtime on Windows (installed — working).
- **Stats engine**: numpy-only (scipy is not in the venv) — `np.polyfit` + manual R².
- **Backend reload**: `just run-backend` scopes the watcher to `app/` and excludes `*.db*`, so the dev DB churn (poller writes to `scada_reporter.db` + WAL/SHM) no longer triggers endless reloads. If reload still wedges (the `--reload` reloader spawns a child, so a port-only kill leaves it respawning), use `just restart-backend` — it stops all `python` processes, then starts clean.
- Fast package install with `uv pip install ...`
- pre-commit hooks are active — ruff + mypy + format checks run on every commit
- Update the frontend TS client: `just gen-client` while the backend is running
- **Test DB isolation**: tests share one in-memory SQLite engine (StaticPool); an autouse fixture in `tests/conftest.py` clears every table before each test (FK-safe order), so tests are order-independent. Do **not** rely on data written by another test. Savepoint-rollback isolation does **not** work here — pysqlite never emits a real outer `BEGIN`, so app commits hit the DB and an outer rollback is a no-op.
- **codegraph** (semantic code intelligence): the repo is indexed (`.codegraph/`, gitignored). Prefer `codegraph explore "<question/symbols>"` and `codegraph node <symbol|file>` over grep/find when locating or understanding code — they return the blast radius (callers + covering tests) plus verbatim source in one call. The `codegraph_explore`/`codegraph_node` MCP tools load after a Claude Code restart; the shell commands always work.
- **Windows env**: `python3` does not exist — use `python`. Tools/hooks that assume `python3` fall back to a `~/bin/python3.exe` shim.
- **Licensing**: `app/core/license.py` resolves a runtime mode at startup (`initialize_license_state`) — `licensed` / `demo` (read-only, gated, tag-capped) / `full` (no `SCADA_LICENSE_PUBLIC_KEY` ⇒ dev/tests unaffected). Enforcement lives in `app/api/license_guard.py` (feature gates + `max_tags` quota + demo read-only). Admins hot-reload a license via `POST /api/license` (Settings → License). Vendor signs with `scripts/generate_license.py`; deploy guide `docs/license-deployment.md`. Disabled by default; `SCADA_LICENSE_REQUIRED=true` is strict fail-closed.
- **Grafana panels in reports**: templates can attach Grafana panels; report generation renders them via `app/services/grafana_render.py` (Grafana `/render`) into PDF/Excel. Auth: `GRAFANA_SA_TOKEN` (service-account token) or falls back to `GRAFANA_USER`/`GRAFANA_PASSWORD` basic-auth. Renderer service must be running on `:8081`. See `docs/grafana-report-panels.md`.
- **Lab → Grafana dashboard**: `POST /api/grafana/dashboards/from-lab` (feature-gated `grafana`, any authenticated user) generates a Grafana dashboard from a lab sample point — one time-series panel per parameter with min/max limit lines + a latest-values table, uid `sr-lab-{point_id}-{hash}`, overwrite-on-regenerate, querying the `v_lab_timeseries` view. `DELETE /api/grafana/dashboards/{uid}` (admin-only) deletes a managed dashboard. Both endpoints validate uid against `^[A-Za-z0-9_-]+$`.
- **Grafana datasource = frser-sqlite (dev)**: the deployment Grafana queries the backend SQLite directly via the **frser-sqlite-datasource** (`uid` from `settings.GRAFANA_DATASOURCE_UID`, default `scadadb`) — there is no `timescaledb` PostgreSQL datasource. ALL generators (`app/services/grafana_templates.py` — lab + `facility_overview` + `water_quality`) emit frser targets via `_frser_datasource()`/`_frser_target(sql, *, time_series)`. **frser supports NO `$__` macros** — use plain SQL + fixed windows `datetime('now', '-N units')`, epoch `CAST(strftime('%s', col) AS INTEGER) AS time`, and `row_number() OVER (...)` instead of PostgreSQL `DISTINCT ON`. The report-template generator (`build_report_template_dashboard`) stays on PostgreSQL (`{type:"postgres",uid:"timescaledb"}`) — the shared panel helpers' `datasource`/`target` kwargs default to that, so it is unaffected.
- **Grafana series/table labels = tag description**: generated panels label series/rows with the tag's description, not the technical name — shared SQL expr `_TAG_LABEL = COALESCE(NULLIF(t.description, ''), t.name)` in `grafana_templates.py` (falls back to name when empty). Used in the metric column + table label columns of `water_quality`, `facility_overview`, and `build_report_template_dashboard` (lab uses `param_name`, untouched). Tables alias the label `AS "Etiket"`; breach SQL keeps `GROUP BY t.name` (per-tag grouping). Metric timeseries panels also set `fieldConfig.defaults.displayName = "${__field.labels.metric}"` (via `metric_series=True` / `apply_metric_display_name`) to drop frser's `"value <metric>"` legend prefix. The in-app **Trend** chart mirrors this client-side (recharts `Line name` from the tags list, data still keyed by unique `name`).
- **Re-label existing dashboards**: `POST /api/grafana/dashboards/refresh-managed` (admin + `require_writable` + feature-gated `grafana`) walks every managed `sr-*` dashboard and applies `apply_tag_label` (SQL) + `apply_metric_display_name` (panel) **in place**, overwrite-on-write. Idempotent (skips dashboards already labeled, reason `no-op`); per-dashboard failures are collected in `skipped`, whole-Grafana failure → 502. Returns `{updated, skipped}`. Frontend admin button "Panoları güncelle" on the Grafana page.
- **Grafana writes NEED `GRAFANA_SA_TOKEN`**: the backend's bulk writers (`refresh-managed`, `generate`, `from-lab`, `from-report-template`, `delete`) use `render_auth()`/`render_headers()` — **SA token (Bearer) if `GRAFANA_SA_TOKEN` is set, else basic `GRAFANA_USER`/`GRAFANA_PASSWORD`**. Basic-auth bursts (refresh-managed loops over N dashboards) trip Grafana's **login-rate/brute-force throttle → intermittent HTTP 403** (auth falls to anonymous, which lacks `dashboards:write`); Bearer/SA tokens bypass that path. So for reliable writes set `GRAFANA_SA_TOKEN` (Editor-role service account) in `.env`. Create via Grafana UI (Administration → Service accounts) or API (`POST /api/serviceaccounts` then `/{id}/tokens`). `render_auth` already prefers the SA token; just provide one.
- **Live Metrics database stats**: `GET /api/dashboard/database` (any authenticated user) returns DB size (dialect-aware: SQLite file + `-wal`/`-shm`, or `pg_database_size`), `total_readings`, `earliest`, last 24h/7d/30d counts, `tag_count`, per-table row counts (fixed allowlist), daily write rate, and estimated monthly growth. The Live Metrics (`Canlı Metrikler`) page renders this in a "Veritabanı" section with a **manual "Yenile" button** (no auto-polling — the `count(*)` over ~54M rows runs only on load + click).
- **Backup / restore**: app-managed DB snapshots. Engine `app/services/backup_engine.py` — SQLite `VACUUM INTO` (consistent, WAL-safe) / PostgreSQL `pg_dump -Fc`, sha256 + `PRAGMA integrity_check`, restore via the sqlite3 online-backup API, retention prune. `Backup` model + API `app/api/backup.py` (`/api/backup` create/list/download/delete + `/{id}/restore`) — **admin + `require_writable` gated** (blocked in demo mode); restore needs `{"confirm":"RESTORE"}`, takes a pre-restore safety snapshot, then `engine.dispose()`. Nightly APScheduler job `db_backup` + retention (`BACKUP_DIR`/`BACKUP_RETENTION_DAYS`/`BACKUP_SCHEDULE_CRON`/`RUN_BACKUP_SCHEDULER`). Frontend `SettingsBackupCard` (admin; download is an **authenticated blob fetch**, not a bare anchor — the endpoint needs the Bearer token). Ops guide `docs/backup-restore.md`. Physical PITR (pgBackRest/WAL-G) is the recommended prod path and is tracked separately.
- **Ingest / query perf** (measured on this box — `bench_ingest.py`, `bench_sqlite_pragmas.py`):
  - **Poller write path** `write_readings` (`app/collector/poller.py`): dialect-guarded. PostgreSQL + `S7_PG_COPY_INGEST=true` (**default OFF** — verify TimescaleDB COPY-to-hypertable + smoke-test first) uses asyncpg `COPY` (`_copy_readings`, ~3.18× faster than INSERT); else SQLAlchemy bulk INSERT (`_insert_readings`). `unique_violation` (sqlstate 23505) → batch rolled back, returns 0; any other COPY error → logs + falls back to INSERT (no data loss). **`ts` is normalized to naive UTC** in `write_readings` — `tag_readings.timestamp` is `timestamp without time zone` and asyncpg rejects a tz-aware datetime on BOTH paths (SQLite dev masked this; real-PG smoke caught it).
  - **Standalone `tag_readings.timestamp` index dropped on PostgreSQL only** (migration `b8c9d0e1f2a3`, ~12.5% faster writes — the hypertable partition + composite PK `(tag_id, timestamp)` already cover it); **kept on SQLite** (no hypertable; backs dashboard timestamp scans).
  - **SQLite pragmas** `set_sqlite_pragmas` (`app/core/database.py`): WAL + `synchronous=NORMAL` + `cache_size=-64000` (64 MB) + `mmap_size` 256 MB + `wal_autocheckpoint=1000` (~16% faster reads, bounds WAL growth).
  - **Trend rollup routing**: `trend_range` + `trend_agg` (`app/api/dashboard.py`) send wide windows (>6h) to the matching continuous-aggregate rollup (`tag_readings_1m/5m/1h`) via `_rollup_series_window` instead of scanning raw `tag_readings`; short windows + SQLite/no-rollup fall back to raw transparently (identical `{t,v}` shape).
