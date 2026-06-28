# EKONT SMART REPORT

**Snap7-based SCADA data acquisition and reporting system** for water and wastewater plants.

Collects data directly from Siemens S7-1500 PLCs, stores it in a time-series database, and serves it to users through a React web interface and a REST API. No paid third-party software required.

---

## Features

### Data Acquisition
- Direct connection to Siemens S7-1500 PLCs via **Snap7** (TCP 102, free)
- Multi-PLC support: 3000+ tag catalog, separate IP/rack/slot configuration per PLC
- Periodic batch reads of active tags (default: 5 s)
- Keeps running in **simulation mode** when the PLC is unreachable
- **Built-in OPC UA server** (`opc.tcp://localhost:4840`) publishes latest values

### Web Interface (Frontend — React)

| Page | Description |
|------|-------------|
| **Dashboard** | 3 tabs: Overview (counters), Watchlist (per user + Grafana sync), All Tags (search/filter/pagination) |
| **Trend Chart** | Multi-tag, multi-Y-axis; zoom/pan (Brush + mouse wheel); yellow dashed-line cursor; hover data table; PNG and Excel export; preset save/load |
| **Reports** | Tag/time selection, hourly/daily aggregation, Excel+JSON output; filter presets |
| **Advanced Reports** | Report templates + scheduler + archive (template-based, recurring, download) |
| **Excel Templates** | Upload/inspect Excel templates and generate filled workbooks |
| **Tags** | Tag listing, unit and description editing, active/inactive management |
| **PLC Config** | Add/remove PLCs, manage IP/rack/slot/connection status |
| **PLC Health** | Per-PLC health, incident summary, acknowledgement workflow |
| **Lab Data Entry** | Manual entry of lab analysis results (single-sample, batch grid, Excel/CSV import, records); hybrid parameter + sample-point catalog; mirrors values into SCADA tag readings |
| **Live Metrics** | Poller throughput + deadband savings; **Database** section (size, total/earliest readings, last 24h/7d/30d counts, tag count, per-table rows, daily rate, est. growth) with a manual refresh button |
| **Monitoring & Analytics** | Prometheus metrics view + embedded Grafana dashboards; generate a Grafana dashboard from a lab sample point or a project template (`facility_overview` / `water_quality`); admin delete of managed dashboards. Generators emit frser-sqlite panels |
| **Settings** | User preferences (theme, language, trend chart height); License status + admin license upload; Lab Catalog (admin) |
| **Users** | Admin-only user management |

### Backend API (`/api/*`)

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/api/auth` | Login (OAuth2 form-data), token |
| Tags | `/api/tags` | Tag CRUD, reading history |
| Dashboard | `/api/dashboard` | Overview, current values, trend query, database statistics (`/database`) |
| Realtime | `/api/dashboard/stream`, `/api/dashboard/logs/stream` | SSE latest-value and log streams |
| Reports | `/api/reports` | Report generation and history |
| Advanced Reports | `/api/advanced-reports` | Template CRUD, scheduler, archive, download |
| Excel Templates | `/api/excel-templates` | Template inspection and workbook generation |
| PLC | `/api/plc` | PLC configuration CRUD |
| PLC Health | `/api/plc/health`, `/api/plc/incidents/*` | PLC health state and incident tracking |
| Groups / Annotations | `/api/groups`, `/api/annotations` | Tag grouping and time-series annotations |
| Users / Audit | `/api/users`, `/api/audit` | Admin user management and audit trail |
| AI | `/api/ai` | AI-assisted query, anomaly, prediction, report, and resolve helpers |
| Query | `/api/query` | Read-only SQL query (SELECT / WITH / EXPLAIN) |
| Explore | `/api/explore` | Schema and tag catalog discovery |
| Lab | `/api/lab` | Lab parameters, sample points, samples, batch entry, Excel/CSV import (16 endpoints) |
| Grafana Dashboards | `/api/grafana/dashboards` | Generate from lab sample point or project template (POST); delete by uid (DELETE — admin) |
| Compliance | `/api/compliance` | Permit profiles, deterministic rule evaluation, compliance events, notes, status transitions, overview |
| License | `/api/license` | License status (GET); admin upload/replace (POST) and revert-to-demo (DELETE) |
| Health | `/live`, `/ready`, `/health`, `/metrics` | Liveness, readiness, system health, Prometheus metrics |

### Security
- JWT-based authentication (OAuth2 Password Flow — **form-data**, not JSON)
- Role-based authorization: `operator` and `admin`
- Default users: `admin / admin123`, `operator / operator123`

### Licensing (optional, commercial)
- Signed-JWT license (RS256/ES256): the vendor signs with a private key; the backend verifies with the env-provisioned public key.
- **Runtime modes**: `licensed` (features/quota per claims) · `demo` (read-only, premium features off, tag list capped) · `full` (no public key configured — development default).
- **Feature gates**: `advanced_reports`, `grafana` sync, realtime SSE, tag `export`; plus a `max_tags` quota.
- **In-app activation**: admins upload/replace/remove a license from **Settings → License** with hot-reload (no restart); a sidebar badge shows the active mode.
- Generate keys and issue licenses with `just license`; deployment details in `docs/license-deployment.md`. Disabled by default — dev and tests are unaffected.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.14, FastAPI, Uvicorn |
| S7 PLC connection | python-snap7 (free, direct TCP 102) |
| Built-in OPC UA | asyncua |
| Database (dev) | SQLite + aiosqlite (no Docker needed) |
| Database (prod) | PostgreSQL 16 + TimescaleDB |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Report generation | openpyxl, WeasyPrint (PDF — requires GTK3) |
| Validation | Pydantic v2 |
| Frontend | React 19, Vite, Tailwind CSS v4, TanStack Query |
| Charts | Recharts |
| Internationalization | i18next — 5 locales (en/tr/ru/de/ar), Arabic drives RTL |
| Testing | pytest (async, parallel via xdist); Vitest + Testing Library + Playwright (frontend) |
| Package managers | uv (backend), pnpm (frontend) |
| Task runner | just |
| Containers | Docker Compose for local infrastructure |

---

## Project Structure

```
scada-reporter/
├── backend/                    # Python FastAPI backend (:8001)
│   ├── app/
│   │   ├── api/                # REST endpoints
│   │   │   ├── auth.py         # Login / token
│   │   │   ├── dashboard.py    # Overview, current values, trend
│   │   │   ├── tags.py         # Tag CRUD
│   │   │   ├── reports.py      # Basic reporting
│   │   │   ├── advanced_reports.py  # Template / scheduler / archive
│   │   │   ├── plc.py          # PLC configuration CRUD
│   │   │   ├── query.py        # Read-only SQL
│   │   │   ├── explore.py      # Schema / catalog discovery
│   │   │   ├── groups.py       # Tag groups
│   │   │   ├── annotations.py  # Time-series annotations
│   │   │   ├── users.py        # Admin user management
│   │   │   ├── audit.py        # Audit log
│   │   │   └── ai.py           # AI helper endpoints
│   │   ├── collector/
│   │   │   ├── s7_collector.py # Snap7 S7-1500 connection
│   │   │   ├── opcua_server.py # Built-in OPC UA server
│   │   │   └── poller.py       # Periodic read loop
│   │   ├── core/
│   │   │   ├── config.py       # Environment variables
│   │   │   ├── database.py     # Async SQLAlchemy engine
│   │   │   └── security.py     # JWT / hashing
│   │   ├── models/
│   │   │   ├── tag.py          # Tag + TagReading
│   │   │   ├── user.py         # User
│   │   │   ├── plc_config.py   # PLC configuration
│   │   │   ├── watchlist.py    # Per-user watchlist
│   │   │   ├── report_history.py    # Report history
│   │   │   ├── report_template.py   # Advanced report template
│   │   │   ├── scheduled_report.py  # Scheduled report
│   │   │   └── report_archive.py    # Archived reports
│   │   ├── services/           # Reports, templates, scheduler, stats, AI helpers
│   │   └── main.py             # FastAPI application entry point
│   ├── tests/                  # pytest async tests
│   ├── alembic/                # DB migration files
│   ├── seed_users.py           # Default user creation
│   ├── pyproject.toml          # pytest / ruff / mypy config
│   └── requirements.txt
├── frontend/                   # React + Vite (:5173)
│   ├── src/
│   │   ├── pages/              # Dashboard, Trend, Reports, AdvancedReports,
│   │   │                       # Tags, PlcConfig, PlcHealth, Metrics, Grafana,
│   │   │                       # ExcelTemplates, Users, Settings, Login
│   │   ├── context/            # AuthContext, SettingsContext (localStorage)
│   │   ├── components/         # Layout (sidebar nav)
│   │   └── api/                # Generated OpenAPI TypeScript client
│   └── openapi-ts.config.ts    # TS client generator config
├── agent-harness/              # Agent-native CLI (Click + JSON + REPL)
│   └── src/scada_reporter_cli/
├── commands/                   # Claude Code slash commands
├── guides/                     # Agent methodology guides
└── AGENTS.md                   # Agent usage guide
docker/                         # TimescaleDB + Redis + Prometheus; Grafana optional profile
```

---

## Setup and Running

### Requirements
- **Python 3.14+ (single supported baseline)** — managed with uv
- Node.js 24+, pnpm
- just (task runner)
- Siemens S7-1500 PLC (or simulation mode)

### Quick Start

```bash
# Install dependencies
just install

# Create default users (admin/admin123, operator/operator123)
just seed-users

# Start backend + frontend in parallel
just dev
```

Application:
- Backend: `http://localhost:8001` — API docs: `http://localhost:8001/docs`
- Frontend: `http://localhost:5173`

### Commands

```bash
# Development
just run-backend      # Backend only (hot reload)
just run-frontend     # Frontend only (Vite)

# Database
just migrate          # Apply migrations
just makemigration msg="description"
just seed-tags        # Add demo tag set
just seed-users       # Default users (admin + operator)
just seed-catalog     # Load tag catalog from WinCC xlsx

# Test & Quality
just test             # pytest backend tests
just test-cov         # Coverage report
just lint             # ruff
just typecheck        # mypy
just backend-check    # Backend lint + format check + typecheck + tests
just frontend-check   # Frontend typecheck + lint + tests
just cli-check        # Agent CLI tests
just mcp-check        # MCP server tests
just check            # Backend + frontend + CLI + MCP checks

# Tools
just dump-openapi     # Write frontend/openapi.json from backend app import
just gen-client       # dump-openapi + OpenAPI → TypeScript client
just test-plc         # PLC connection test
just docker-up        # Start local infra: TimescaleDB + Redis + Prometheus + Portainer
just run-collector    # Start collector process separately (prod topology)
just license "keygen --type rsa"    # License: generate signing keypair / issue licenses
```

### Environment Variables (`.env`)

```env
# Dev/local infra default (PostgreSQL via just docker-up)
DATABASE_URL=postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter

# Optional SQLite development mode
# DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db

SECRET_KEY=change-this-in-production-32-chars-minimum
ACCESS_TOKEN_EXPIRE_MINUTES=480

# API/collector topology
RUN_COLLECTOR=True

# S7 PLC (simulation mode is used when PLC is unreachable)
S7_HOST=192.168.112.50
S7_RACK=0
S7_SLOT=1
```

Copy and edit the `.env.example` file:
```bash
copy .env.example scada-reporter/backend/.env
```

---

## Agent CLI (`scada`)

Coding agents (Claude Code etc.) can use the REST API through the `scada` CLI.

```bash
just install-agent        # Install

scada auth login admin    # Login
scada tags list --json-output    # Tag list
scada dashboard overview  # Overview
scada query run "SELECT name, value FROM tags LIMIT 5" --json-output
scada explore schema      # DB schema
scada compliance overview --json-output   # Permit-compliance period readiness
scada shell               # Python REPL (data loaded)
```

Detailed guide: `scada-reporter/AGENTS.md`

---

## Notes

- **OAuth2 login**: the `/api/auth/token` endpoint expects **form-data** (not JSON) — use `curl -d "username=admin&password=admin123"`
- **Simulation mode**: the backend runs fine when no PLC is present or reachable
- **WeasyPrint PDF**: requires the GTK3 runtime on Windows
- **pre-commit hooks**: ruff + mypy + format checks run on every commit
- **Licensing**: disabled by default. With a public key configured but no valid license, the backend runs in **demo mode** (read-only). Upload a license from Settings → License, or set `SCADA_LICENSE_*` env vars (see `.env.production.example` and `docs/license-deployment.md`)
