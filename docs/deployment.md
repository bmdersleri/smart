# Production Deployment Guide

EKONT SMART REPORT — process-based (non-container) production deployment.

> **Scope**: This guide covers running the API, collector, and frontend as native OS
> processes. Docker is used only for local dev infrastructure (TimescaleDB + Redis +
> Prometheus + Portainer; Grafana is optional via profile). Dockerfiles and a
> production compose file are intentionally out of scope;
> see [DOCKER.md](../DOCKER.md) for the dev-infra setup.

---

## Architecture Overview

Four independent processes serve the system in production:

| Process | Command | Port | Notes |
|---------|---------|------|-------|
| **API server** | `gunicorn -k uvicorn.workers.UvicornWorker app.main:app -w <N> -b 0.0.0.0:8001` | 8001 | `RUN_COLLECTOR=False`, `RUN_SCHEDULER=False` — multiple workers safe |
| **Scheduler** | `python -m app.scheduler.runner` | n/a | `RUN_COLLECTOR=False`, `RUN_SCHEDULER=True` — **single instance only** |
| **Collector** | `python -m app.collector.runner` | 4840 (OPC UA) | `RUN_COLLECTOR=True` — **single instance only** |
| **Frontend** | Served from `dist/` as static files | any static port | Built with `pnpm build` |

---

## 1. Prerequisites

- Python 3.14 virtual environment created and dependencies installed:
  ```bash
  cd scada-reporter/backend
  uv pip install -r requirements.lock   # or: pip install -r requirements.txt
  ```
- Node.js 24+ and pnpm installed for the frontend build.
- PostgreSQL (TimescaleDB) reachable from the backend host.
- Redis reachable if you use Redis-backed services elsewhere in the stack.

---

## 2. Environment Configuration

Copy the production template and fill in all values:

```bash
cp scada-reporter/backend/.env.production.example scada-reporter/backend/.env
```

Key variables (the application **refuses to start** in `ENVIRONMENT=production` if
these are missing or still set to insecure defaults — enforced by `config_errors()` in
`app/core/config.py`):

| Variable | Requirement |
|----------|-------------|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | Real random key — generate with `openssl rand -hex 32` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` or lower is recommended for production bearer tokens |
| `DATABASE_URL` | `postgresql+asyncpg://USER:STRONG_PASS@db-host:5432/scada_reporter` — no demo password, no localhost |
| `CORS_ORIGINS` | Explicit allowed origins, e.g. `https://scada.example.com` — no wildcard |
| `AUTO_CREATE_TABLES` | `False` — schema is managed via Alembic |
| `RUN_COLLECTOR` | `False` for API workers; `True` for the collector process |
| `RUN_SCHEDULER` | `False` for API workers; `True` for the scheduler process |

Additional variables configured in `.env.production.example`:
- `ACCESS_TOKEN_EXPIRE_MINUTES` — bearer-token TTL; keep short in production to limit replay exposure
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` — PostgreSQL connection pool
- `REDIS_URL` — Redis-backed services / cache (if enabled)
- `SENTRY_DSN` — optional error tracking
- `FACILITY_NAME` — appears in PDF/Excel report headers

Security note:
- Current frontend auth uses bearer tokens persisted in `localStorage`, which is exposed to any script running in the page context. Keep the app behind HTTPS and a restrictive CSP so injected or third-party scripts cannot silently read tokens.
- Follow-up work should evaluate moving session storage to `HttpOnly` cookies with CSRF protections if the browser auth flow changes.

---

## 3. Database Schema

Run migrations before starting any application process:

```bash
cd scada-reporter/backend
alembic upgrade head
```

`AUTO_CREATE_TABLES=False` prevents SQLAlchemy from silently creating tables outside of
Alembic control. Never skip the migration step in production.

---

## 4. Process Topology

### 4a. API Server (multiple workers allowed)

The API process handles all HTTP requests. With `RUN_COLLECTOR=False` and
`RUN_SCHEDULER=False` the Snap7 PLC poller, OPC UA server, and APScheduler do
**not** start, so running multiple Gunicorn workers is safe.

**Recommended (Gunicorn + Uvicorn workers):**

```bash
cd scada-reporter/backend
RUN_COLLECTOR=False RUN_SCHEDULER=False gunicorn \
  -k uvicorn.workers.UvicornWorker \
  app.main:app \
  -w 4 \
  -b 0.0.0.0:8001 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
```

Replace `-w 4` with `(2 × CPU_COUNT) + 1` as a starting point.

**Alternative (Uvicorn with multiple workers):**

```bash
cd scada-reporter/backend
RUN_COLLECTOR=False RUN_SCHEDULER=False uvicorn app.main:app \
  --workers 4 \
  --host 0.0.0.0 \
  --port 8001
```

Both forms respect all settings from `.env` (loaded by `pydantic-settings`).

### 4b. Scheduler Process (single instance only)

The scheduler process owns APScheduler and must run exactly once in the deployment.
Set `RUN_SCHEDULER=True` for this role and keep `RUN_COLLECTOR=False` so the
process does not also start PLC collection.

```bash
cd scada-reporter/backend
RUN_COLLECTOR=False RUN_SCHEDULER=True python -m app.scheduler.runner
```

What it starts:
- `start_scheduler(settings.DATABASE_URL)` — APScheduler with the shared job store
- A signal-aware wait loop that keeps exactly one scheduler process alive

This process does not start the API server or the collector.

### 4c. Collector Process (single instance only)

The collector runs the Snap7 PLC poller and the built-in OPC UA server on port 4840.

> **Warning**: Run exactly ONE instance of the collector. Running it on multiple hosts
> would cause multiple simultaneous PLC polling loops writing duplicate readings to the
> database and multiple conflicting OPC UA servers competing for port 4840.

```bash
cd scada-reporter/backend
RUN_COLLECTOR=True python -m app.collector.runner
```

What it starts (see `app/collector/runner.py`):
- `poll_loop()` — Snap7 S7 tag poller (tick interval: `S7_POLL_INTERVAL` seconds)
- `opcua_server` — built-in OPC UA server on `opc.tcp://0.0.0.0:4840`

The collector writes to the same TimescaleDB instance as the API. No HTTP port is exposed.

If no PLC is reachable the collector enters simulation mode and continues running.

### 4d. Frontend (static files)

Build once, serve with any static file server (nginx recommended):

```bash
cd scada-reporter/frontend
pnpm install
pnpm build        # tsc -b && vite build → dist/
```

The output directory is `scada-reporter/frontend/dist/`. Serve it from nginx (see
Section 5) or any static server (`python -m http.server`, Caddy, etc.).

---

## 5. Reverse Proxy — Nginx Example

A single nginx vhost that:
- Serves the frontend static bundle
- Proxies `/api` requests to the Gunicorn/Uvicorn backend
- Disables buffering on SSE streaming endpoints
- Restricts `/metrics` to internal networks

```nginx
server {
    listen 80;
    server_name scada.example.com;

    # Redirect all HTTP to HTTPS (recommended for production)
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name scada.example.com;

    ssl_certificate     /etc/ssl/certs/scada.crt;
    ssl_certificate_key /etc/ssl/private/scada.key;

    # --- Frontend static files ---
    root /opt/scada/frontend/dist;
    index index.html;

    # SPA fallback: unknown paths serve index.html (React Router handles routing)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # --- Backend API ---
    location /api/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # --- SSE streaming endpoints (disable buffering) ---
    # /api/dashboard/stream and /api/dashboard/logs/stream use Server-Sent Events.
    # Buffering must be disabled or the browser never receives frames.
    location ~ ^/api/dashboard/(logs/)?stream {
        proxy_pass             http://127.0.0.1:8001;
        proxy_set_header       Host              $host;
        proxy_set_header       X-Real-IP         $remote_addr;
        proxy_set_header       X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header       X-Forwarded-Proto $scheme;
        proxy_buffering        off;
        proxy_cache            off;
        proxy_read_timeout     3600s;   # SSE connections are long-lived
        proxy_http_version     1.1;
        proxy_set_header       Connection "";
    }

    # --- Health probes (accessible from load balancer) ---
    location ~ ^/(live|ready|health)$ {
        proxy_pass http://127.0.0.1:8001;
    }

    # --- Prometheus metrics (restrict to internal network) ---
    location /metrics {
        proxy_pass http://127.0.0.1:8001;
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        allow 127.0.0.1;
        deny  all;
    }
}
```

---

## 6. Health Checks

Three health endpoints are available on the API server (all at the root, no `/api`
prefix — see `app/main.py`):

| Endpoint | Use case | Returns |
|----------|----------|---------|
| `GET /live` | Liveness — process alive? | `{"status": "alive"}` — always 200 |
| `GET /ready` | Readiness — DB + Alembic + scheduler OK? | 200 or 503 with per-check detail |
| `GET /health` | Human-readable PLC/collector summary | JSON with PLC counts and scheduler state |

### `/ready` response structure

```json
{
  "status": "ready",
  "role": {
    "collector_enabled": false,
    "scheduler_enabled": false
  },
  "checks": {
    "db": true,
    "alembic_head": true,
    "scheduler": "disabled"
  }
}
```

Returns `503` with `"status": "not_ready"` and the failing check set to `false` if any
mandatory dependency is down. When `RUN_SCHEDULER=False`, readiness treats the
scheduler check as disabled rather than failing the probe.

### Example usage

```bash
# Liveness (use as process supervisor heartbeat)
curl -f http://localhost:8001/live

# Readiness (use as load-balancer health check gate)
curl -f http://localhost:8001/ready

# Human-readable PLC/collector summary
curl http://localhost:8001/health
```

### Load-balancer / systemd configuration

```ini
# systemd service health check (ExecStartPost or StartLimitBurst approach)
ExecStartPost=/usr/bin/curl -sf http://localhost:8001/ready

# nginx upstream health check (nginx Plus or community module)
# check interval=5000ms rise=2 fall=3 timeout=2000ms type=http;
# check_http_send "GET /ready HTTP/1.0\r\n\r\n";
# check_http_expect_alive http_2xx;
```

---

## 7. Process Management

Use a process manager to keep processes alive and restart them on failure.

### Systemd example — API Server

```ini
# /etc/systemd/system/scada-api.service
[Unit]
Description=EKONT SMART REPORT API Server
After=network.target postgresql.service

[Service]
Type=exec
User=scada
WorkingDirectory=/opt/scada/scada-reporter/backend
EnvironmentFile=/opt/scada/scada-reporter/backend/.env
Environment=RUN_COLLECTOR=False
Environment=RUN_SCHEDULER=False
ExecStart=/opt/scada/scada-reporter/backend/.venv/bin/gunicorn \
    -k uvicorn.workers.UvicornWorker \
    app.main:app \
    -w 4 \
    -b 0.0.0.0:8001 \
    --timeout 120
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Systemd example — Collector

```ini
# /etc/systemd/system/scada-collector.service
[Unit]
Description=EKONT SMART REPORT Collector (Snap7 + OPC UA)
After=network.target postgresql.service scada-api.service

[Service]
Type=exec
User=scada
WorkingDirectory=/opt/scada/scada-reporter/backend
EnvironmentFile=/opt/scada/scada-reporter/backend/.env
Environment=RUN_COLLECTOR=True
ExecStart=/opt/scada/scada-reporter/backend/.venv/bin/python -m app.collector.runner
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable --now scada-api scada-collector
```

---

## 8. Startup Sequence

Follow this order when bringing up the system from scratch:

1. Start Docker infrastructure: `just docker-up` (PostgreSQL + Redis)
2. Apply migrations: `cd scada-reporter/backend && alembic upgrade head`
3. Seed default users (first install only): `just seed-users`
4. Start API server: `systemctl start scada-api` (or gunicorn command above)
5. Verify readiness: `curl -f http://localhost:8001/ready`
6. Start collector: `systemctl start scada-collector`
7. Verify health: `curl http://localhost:8001/health`

---

## 9. Backup and Restore

See [docs/backup-recovery.md](backup-recovery.md) for full backup/restore procedures
(TimescaleDB continuous archiving, WAL-G / pg_dump, and restore runbook).

---

## 10. Related Documentation

| Document | Purpose |
|----------|---------|
| [DOCKER.md](../DOCKER.md) | Local dev infrastructure (TimescaleDB + Redis + Prometheus + Portainer; optional Grafana profile) |
| [docs/backup-recovery.md](backup-recovery.md) | Database backup, WAL archiving, and restore |
| `scada-reporter/backend/.env.production.example` | Full env var reference with comments |
| `scada-reporter/backend/app/core/config.py` | All config fields and `config_errors()` validation |
