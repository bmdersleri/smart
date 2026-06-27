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
- **Live Metrics database stats**: `GET /api/dashboard/database` (any authenticated user) returns DB size (dialect-aware: SQLite file + `-wal`/`-shm`, or `pg_database_size`), `total_readings`, `earliest`, last 24h/7d/30d counts, `tag_count`, per-table row counts (fixed allowlist), daily write rate, and estimated monthly growth. The Live Metrics (`Canlı Metrikler`) page renders this in a "Veritabanı" section with a **manual "Yenile" button** (no auto-polling — the `count(*)` over ~54M rows runs only on load + click).
