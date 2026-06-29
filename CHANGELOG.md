# Changelog

All notable changes to EKONT SMART REPORT are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed

- **Dashboard and Live Metrics merged into one tabbed page** — the standalone
  `/metrics` ("Canlı Metrikler") page was folded into the Dashboard. The tab bar
  is now **Overview · Watchlist · Tags · System · Database**. `Metrics.tsx` was
  removed, `/metrics` redirects to `/`, and the sidebar "Canlı Metrikler" entry
  is gone. Each tab fetches only while open (`active`-gated): the **System** tab
  (poller stats, deadband savings, PLC read-latency table, live log console)
  polls 2s/10s and streams the console only when active; the **Database** tab
  keeps its manual "Yenile" refresh. New tab labels `tab_system`/`tab_database`
  in 5 languages (EN/TR/DE/RU/AR).

### Added

- **Database statistics on Live Metrics** — `GET /api/dashboard/database` (any
  authenticated user) returns DB size (dialect-aware: SQLite file + `-wal`/`-shm`
  siblings, or PostgreSQL `pg_database_size`), total `tag_readings`, earliest
  reading, last 24h/7d/30d counts (parameterized cutoffs), tag count, per-table
  row counts (fixed allowlist), daily write rate, and estimated monthly disk
  growth. The Live Metrics (`Canlı Metrikler`) page shows a "Veritabanı" section
  with a **manual "Yenile" refresh button** — no auto-polling, so the `count(*)`
  over millions of rows runs only on load + click. `formatBytes` + i18n in 5
  languages (EN/TR/DE/RU/AR).

- **Configurable lab-entry timezone** — lab sample timestamps are entered and
  displayed in a configurable IANA timezone (default Istanbul), set from the
  Settings page; stored as UTC, converted two-pass for correct DST-zone
  wall-clock. Fixes the ~3-hour offset on entry.

- **Lab Data Entry & Tracking** — manual entry of laboratory analysis results
  alongside automatic SCADA/PLC data.
  - **4 entry modes**: single-sample form, batch/table grid, Excel/CSV import
    (column-mapping UI + per-row error tolerance), and Records tab with
    edit/delete for authorized users.
  - **Hybrid catalog**: admin-managed parameters and sample points; operators
    can add new entries on the fly (`approved=false`) pending admin approval.
  - **`mirror_to_tag_id`**: a lab parameter can mirror its values into
    `tag_readings` so it appears on existing SCADA Grafana panels and is
    selectable by Advanced Reports — no new report generator code.
  - **`v_lab_timeseries` view** joining lab tables; provisioned Grafana
    `lab-quality` dashboard with point/parameter template variables, threshold
    lines, and a latest-values table (requires PostgreSQL/TimescaleDB; view is
    SQLite-portable for tests).
  - **Permissions**: entry = operator + admin; edit/delete = admin or record
    owner (`entered_by`); catalog approve = admin. Edit/delete are audited
    (`lab.sample.update` / `lab.sample.delete` in `audit_log`).
  - **API**: 16 endpoints under `/api/lab/` (parameters, sample-points,
    samples, batch, import preview + commit).
  - **Frontend**: Lab Data Entry page with 4 tabs + i18n in 5 languages
    (EN/TR/DE/RU/AR); Lab Catalog card in Settings (admin).

- **Grafana dashboard generator from lab data** — `POST /api/grafana/dashboards/from-lab`
  (feature-gated `require_feature("grafana")`; any authenticated user): select a lab sample
  point and parameters on the Monitoring & Analytics page → generates a Grafana dashboard with
  one time-series panel per parameter (min/max limit lines) plus a latest-values table, uid
  `sr-lab-{point_id}-{hash}`, overwrite-on-regenerate; queries the `v_lab_timeseries` view
  via the frser-sqlite datasource. uid allowlist `^[A-Za-z0-9_-]+$` prevents injection.

- **Grafana dashboard delete** — `DELETE /api/grafana/dashboards/{uid}` (admin-only:
  `require_role("admin")` + `require_writable` + `require_feature("grafana")`): admin-only ✕
  delete control on each dashboard tab in the Monitoring & Analytics page with a confirm step.
  uid validated against `^[A-Za-z0-9_-]+$` (traversal/SSRF guard); Grafana 404→404, provisioned
  dashboards 400/412→409, other errors→502.

- **Commercial licensing** — signed-JWT license system (asymmetric RS256/ES256):
  vendor signs with a private key, the backend verifies with the env-provisioned
  public key at startup.
  - **Runtime modes**: `licensed` (features/quota per claims), `demo` (read-only,
    premium features off, tag visibility capped at `SCADA_LICENSE_DEMO_MAX_TAGS`),
    and `full` (no public key configured — dev). `SCADA_LICENSE_REQUIRED=true`
    keeps strict fail-closed startup.
  - **Enforcement**: `max_tags` quota on tag create/import; feature gates on
    `advanced_reports`, `grafana` sync, realtime SSE, and tag `export`.
  - **In-app management**: `GET/POST/DELETE /api/license` — admins upload/replace/
    remove a license from **Settings → License** with hot-reload (no restart);
    dashboard sidebar **license badge** shows the active mode.
  - **Generator + docs**: `scripts/generate_license.py` (`just license`) for key
    generation and license issuing; `docs/license-deployment.md` deployment guide.

### Fixed

- **Service-worker kill-switch** — replaced the PWA service worker (which intermittently served
  a stale cached HTTP 401 response to the `/grafana-api` proxy on the Monitoring & Analytics
  page) with a self-unregistering stub; the app no longer registers a service worker.
- **Vite dev-proxy basic-auth** — the `/grafana-api` dev proxy now sends Grafana basic-auth
  (`GRAFANA_USER`/`GRAFANA_PASSWORD`) so the dashboard list loads correctly even when Grafana
  anonymous Viewer access is disabled.

---

## [1.0.0] - 2026-06-21

### Added

- **Agent CLI + MCP consolidation (Spec 1)** — scada-core shared package; agent harness and MCP server both consume it; workflow prompts + read-only scada:// resources added to MCP server.
- **In-app write capabilities (Spec 2)** — full implementation plan for tag management, PLC config, and report scheduling mutations via the REST API (9-task, 3-phase plan).
- **PLC health monitoring** — real-time health tracker fed by the poller; hysteresis-based alert state machine; per-PLC incident log; health/incidents/summary/ack API endpoints; webhook + email notification channels; daily prune job; frontend PLC Health page with alert badge.
- **Tag pagination** — Tag Management table paginated (configurable page size + page jump) to prevent full-list render freeze on large catalogs.
- **Audit log** — `AuditLog` model; `record_audit` on admin user mutations; `GET /api/audit` endpoint.
- **RBAC hardening** — `Literal` role schemas + DB check-constraint; frontend `UserRole` union.
- **Auth hardening** — in-process login rate limit on `/token` and `/login`; token versioning (password reset/deactivate invalidates old JWTs); short-lived scoped stream token for SSE (drops long-lived JWT from SSE URLs).
- **Liveness + readiness** — `/live` and `/ready` (DB + Alembic head + scheduler) health endpoints; HTTP/pool metrics.
- **OpenAPI contract freshness** — generated OpenAPI types from committed schema; `client.ts` uses them; CI `contract-freshness` job asserts no drift.
- **Observability** — Prometheus scrape config; Grafana provisioned dashboards (metrics + TimescaleDB SQL).
- **Process-based production deployment guide** — `docs/deployment.md` (API/collector/frontend, no Docker required for prod).
- **Backup/restore/DR runbook** — `docs/backup-recovery.md` with retention and rollup policy.
- **Release policy** — `docs/release-policy.md`; semver rules; single-product version strategy; tag-triggered CI release workflow.
- **CHANGELOG** — this file, in Keep a Changelog format.

### Changed

- **Grafana generators → frser-sqlite datasource**: the `facility_overview` and
  `water_quality` dashboard generators (`app/services/grafana_templates.py`) now
  emit frser-sqlite panels instead of PostgreSQL, matching the deployment Grafana
  (no `timescaledb` datasource exists). PostgreSQL macros (`$__timeGroupAlias`,
  `$__timeFilter`, `$__time`), `now() - INTERVAL`, `EXTRACT(EPOCH ...)`, and
  `DISTINCT ON` are replaced with fixed windows (`datetime('now', '-24 hours')` /
  `'-7 days'`), `strftime('%s', ...)` epoch columns, manual time buckets, and
  `row_number() OVER (...)` latest-value subqueries. Shared panel helpers gained
  opt-in `datasource`/`target` kwargs (PostgreSQL-preserving defaults), so the
  report-template generator stays on PostgreSQL unchanged. `_lab_datasource`
  renamed to `_frser_datasource`.
- **Phase 1 — Baseline alignment**: test infrastructure (pytest-timeout, coverage threshold, seed/collector/bad-quality coverage); CI coverage gate wired in; vacuous tests removed.
- **Phase 2 — Production safety**: CI extended (bandit security scan, contract-freshness, MCP smoke test); `just check` consolidates all checks.
- **Phase 3 — Auth/contract/ops**: auth token versioning, rate limiting, SSE scoped tokens, RBAC Literals, audit log, liveness/readiness, OpenAPI contract CI.
- **Phase 4 — Operational maturity**: Grafana/Prometheus provisioning, deployment + backup docs, AGENTS.md as single authoritative agent guide, version alignment across all components, this release policy + CHANGELOG.
- Backend `pyproject.toml` gains a `[project]` table (`name = "scada-reporter-backend"`, `version = "1.0.0"`, `requires-python = ">=3.14"`).
- All components aligned to version `1.0.0` (scada-core `0.1.0` → `1.0.0`; frontend `0.0.0` → `1.0.0`; backend and agent CLI were already `1.0.0`).

### Fixed

- Bandit B608 false positives justified with `# nosec` (green CI security scan).
- SQL dashboard column names corrected to match CAGG schema (`n`, `avg`).
- Contract-freshness CI job uses explicit `.venv/bin/python` to avoid `VIRTUAL_ENV` pointer mismatch.
- PLC health monitor: `get_running_loop` fix; async test fakes; RTL logical spacing fix.
- Tag pagination: correct `ms-2` RTL utility usage (CI lint).

### Security

- Login rate limiting (config-gated, in-process) prevents brute-force on `/token` and `/login`.
- Token versioning ensures password changes and account deactivation immediately invalidate all outstanding JWTs.
- SSE connections use short-lived scoped tokens instead of long-lived JWTs in URLs.
- Bandit scan integrated into CI (Medium+ severity).

[Unreleased]: https://github.com/bmdersleri/smart/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/bmdersleri/smart/releases/tag/v1.0.0
