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
| **Dashboard** | 3 tabs: Overview (counters), Watchlist (per user), All Tags (search/filter/pagination) |
| **Trend Chart** | Multi-tag, multi-Y-axis; zoom/pan (Brush + mouse wheel); yellow dashed-line cursor; hover data table; PNG and Excel export; preset save/load |
| **Reports** | Tag/time selection, hourly/daily aggregation, Excel+JSON output; filter presets |
| **Advanced Reports** | Report templates + scheduler + archive (template-based, recurring, download) |
| **Tags** | Tag listing, unit and description editing, active/inactive management |
| **PLC Config** | Add/remove PLCs, manage IP/rack/slot/connection status |
| **Settings** | User preferences (e.g. trend chart height, 300–2000 px) |

### Backend API (`/api/*`)

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/api/auth` | Login (OAuth2 form-data), token |
| Tags | `/api/tags` | Tag CRUD, reading history |
| Dashboard | `/api/dashboard` | Overview, current values, trend query |
| Reports | `/api/reports` | Report generation and history |
| Advanced Reports | `/api/advanced-reports` | Template CRUD, scheduler, archive, download |
| PLC | `/api/plc` | PLC configuration CRUD |
| Query | `/api/query` | Read-only SQL query (SELECT / WITH / EXPLAIN) |
| Explore | `/api/explore` | Schema and tag catalog discovery |

### Security
- JWT-based authentication (OAuth2 Password Flow — **form-data**, not JSON)
- Role-based authorization: `operator` and `admin`
- Default users: `admin / admin123`, `operator / operator123`

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
| Testing | pytest (async, parallel via xdist, randomized via pytest-randomly); Vitest + Testing Library + Playwright (frontend) |
| Package managers | uv (backend), pnpm (frontend) |
| Task runner | just |
| Containers | Docker Compose (prod) |

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
│   │   │   └── explore.py      # Schema / catalog discovery
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
│   │   ├── reports/            # Excel / PDF generators
│   │   └── main.py             # FastAPI application entry point
│   ├── tests/                  # pytest async tests (247+, parallel + randomized)
│   ├── alembic/                # DB migration files
│   ├── seed_users.py           # Default user creation
│   ├── pyproject.toml          # pytest / ruff / mypy config
│   └── requirements.txt
├── frontend/                   # React + Vite (:5173)
│   ├── src/
│   │   ├── pages/              # Dashboard, Trend, Reports, AdvancedReports,
│   │   │                       # Tags, PlcConfig, Settings, Login
│   │   ├── context/            # AuthContext, SettingsContext (localStorage)
│   │   ├── components/         # Layout (sidebar nav)
│   │   └── api/                # Generated OpenAPI TypeScript client
│   └── openapi-ts.config.ts    # TS client generator config
├── agent-harness/              # Agent-native CLI (Click + JSON + REPL)
│   └── src/scada_reporter_cli/
├── commands/                   # Claude Code slash commands
├── guides/                     # Agent methodology guides
└── AGENTS.md                   # Agent usage guide
docker/                         # TimescaleDB + Redis + Grafana
```

---

## Setup and Running

### Requirements
- **Python 3.12+ (single supported baseline)** — managed with uv
- Node.js 18+, pnpm
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
just test             # pytest (247+ tests, parallel via xdist, randomized order)
just test-cov         # Coverage report
just lint             # ruff
just typecheck        # mypy
just check            # All checks (CI)

# Tools
just gen-client       # OpenAPI → TypeScript client (while backend running)
just test-plc         # PLC connection test
just docker-up        # Start PostgreSQL + Redis (prod)
```

### Environment Variables (`.env`)

```env
# Dev (SQLite — no Docker needed)
DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db

# Prod (PostgreSQL)
# DATABASE_URL=postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter

SECRET_KEY=change-this-in-production-32-chars-minimum
ACCESS_TOKEN_EXPIRE_MINUTES=480

# S7 PLC (skipped in simulation mode)
S7_HOST=192.168.1.1
S7_RACK=0
S7_SLOT=1
```

Copy and edit the `.env.example` file:
```bash
copy scada-reporter/backend/.env.example scada-reporter/backend/.env
```

---

## Agent CLI (`scada`)

Coding agents (Claude Code etc.) can use the REST API through the `scada` CLI.

```bash
just install-agent        # Install

scada auth login admin    # Login
scada tags list --json    # Tag list
scada dashboard overview  # Overview
scada query run "SELECT name, value FROM tags LIMIT 5" --json
scada explore schema      # DB schema
scada shell               # Python REPL (data loaded)
```

Detailed guide: `scada-reporter/AGENTS.md`

---

## Notes

- **OAuth2 login**: the `/api/auth/token` endpoint expects **form-data** (not JSON) — use `curl -d "username=admin&password=admin123"`
- **Simulation mode**: the backend runs fine when no PLC is present or reachable
- **WeasyPrint PDF**: requires the GTK3 runtime on Windows
- **pre-commit hooks**: ruff + mypy + format checks run on every commit
