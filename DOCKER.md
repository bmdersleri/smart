# Docker Infrastructure Guide

## Overview

This project uses Docker **only for local infrastructure** (database, cache, observability). The application processes (API, collector, frontend) run directly on the host — both in development and in production. See [docs/deployment.md](docs/deployment.md) for the production deployment guide.

---

## Local Infrastructure Usage

The compose file at `scada-reporter/docker/docker-compose.yml` starts four services:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | timescale/timescaledb:latest-pg16 | 5432 | TimescaleDB (PostgreSQL with time-series extensions) |
| `redis` | redis:7-alpine | 6379 | Cache / session store |
| `grafana` | grafana/grafana:latest | 3000 | Dashboards and time-series visualisation |
| `portainer` | portainer/portainer-ce:latest | 9000 | Docker management UI |

### Start / stop

```bash
just docker-up     # docker compose up -d (detached)
just docker-down   # docker compose down
```

> **Dev-only note:** The compose file is intentionally scoped to LOCAL/DEV infrastructure. It does NOT contain app, collector, or frontend services — those run as native OS processes (see [docs/deployment.md](docs/deployment.md)).

---

## Production Topology

### Two-process architecture

In production the backend must be split into two separate processes:

| Process | How to start | `RUN_COLLECTOR` env |
|---------|-------------|---------------------|
| **API server** | `uvicorn app.main:app --workers N` (or `just run-backend`) | `False` (default) |
| **Collector** | `python -m app.collector.runner` (or `just run-collector`) | `True` |

**Why two processes?**
With `uvicorn --workers N` multiple worker processes share the same port. If the collector (Snap7 PLC poller + OPC UA server) ran inside every worker process, you would get N simultaneous PLC polling loops writing duplicate data and N conflicting OPC UA servers on port 4840. Separating the collector into a single dedicated process prevents this.

Set `RUN_COLLECTOR=False` in the API process environment and `RUN_COLLECTOR=True` in the collector process environment.

### Phase 2 production configuration checklist

Production environments must pass validation in `app/core/config.py`. The following env vars must be set to non-default/non-demo values — the application refuses to start in `ENVIRONMENT=production` if they are missing or still set to insecure defaults:

| Variable | Requirement |
|----------|-------------|
| `SECRET_KEY` | Real random key (not the demo default) |
| `DATABASE_URL` | Real PostgreSQL URL (not SQLite) |
| `CORS_ORIGINS` | Explicit allowed origins (not `*`) |
| `AUTO_CREATE_TABLES` | `False` — schema is managed via Alembic |

Apply migrations before starting the API:

```bash
cd scada-reporter/backend
alembic upgrade head
```

See `scada-reporter/backend/.env.production.example` for a complete template.

---

## Overriding Docker Credentials

The compose file ships with **dev-only defaults** (`scada123` / `admin`). These are acceptable for local development but **must be overridden in any non-local environment**.

### Steps

1. Copy the example file:

   ```bash
   cp scada-reporter/docker/.env.example scada-reporter/docker/.env
   ```

2. Edit `scada-reporter/docker/.env` and set real values:

   ```env
   POSTGRES_PASSWORD=<strong-random-password>
   GF_SECURITY_ADMIN_USER=<admin-username>
   GF_SECURITY_ADMIN_PASSWORD=<strong-random-password>
   ```

3. Docker Compose automatically picks up `docker/.env` when you run `docker compose up` from the `scada-reporter/docker/` directory.

> `scada-reporter/docker/.env` is gitignored. Never commit actual secrets. The example file (`docker/.env.example`) is tracked in git and contains only empty placeholders.

---

## Phase 4 Status

### Completed in Phase 4

- **Process-based deployment** (API + collector + frontend as native OS processes, no
  Docker required for the app) — see **[docs/deployment.md](docs/deployment.md)** for
  the full guide including Gunicorn/Uvicorn commands, nginx reverse-proxy config (with
  SSE buffering notes), health-check usage, and systemd service units.
- **Backup and restore** — see **[docs/backup-recovery.md](docs/backup-recovery.md)**
  for TimescaleDB backup procedures, WAL archiving, and restore runbook.

### In progress in Phase 4

- **Grafana provisioning** — datasource and dashboard JSON files for production
  (Task 3).

### Out of scope (explicit decision)

The project uses **process-based deployment** (no application containers). The following
items are intentionally not planned:

- `Dockerfile` for the FastAPI backend
- `Dockerfile` for the frontend (Vite/React)
- A production compose file with `app`, `collector`, and `frontend` services

This is a deliberate architectural choice, not a deferred task. The supported
production path is documented in [docs/deployment.md](docs/deployment.md).
