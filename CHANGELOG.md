# Changelog

All notable changes to EKONT SMART REPORT are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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
