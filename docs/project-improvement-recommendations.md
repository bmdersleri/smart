# EKONT SMART REPORT - Project Improvement Recommendations

**Date:** 2026-06-20
**Scope:** Backend, frontend, agent CLI, `scada-core`, MCP experiments, Docker infrastructure, CI, operations, and documentation.
**Status:** Recommendation document verified against the current repository state. No source code changes are included.

---

## 0. Current Status Update - 2026-06-22

This document is now historical below this section. The repository has already
implemented several items that were open when the original review was written:

- Python baseline is aligned on Python 3.14 across backend, CLI/core metadata,
  local tooling, and CI.
- Backend runtime/dev dependencies are split and committed lock files exist:
  `requirements.lock` and `requirements-dev.lock`.
- Frontend package management is standardized on pnpm with a single
  `pnpm-lock.yaml`.
- CI now covers backend, frontend, agent CLI, OpenAPI contract freshness, and
  MCP server tests.
- The generated OpenAPI TypeScript client is committed under
  `frontend/src/api/generated`.
- Auth now includes JSON login, login rate limiting, token versioning, and a
  short-lived scoped SSE stream token.
- `/live` and `/ready` exist separately from `/health`.
- Production config validation rejects unsafe default secret, demo DB/local DSN,
  and unsafe CORS values; Grafana weak password is warned.
- `AUTO_CREATE_TABLES` and `RUN_COLLECTOR` are explicit settings, and deployment
  docs describe API/collector process separation.
- RBAC role values are constrained by API types and a DB check constraint.
- Grafana datasource/dashboard provisioning and backup/deployment docs exist.

The current active production infrastructure priorities are tracked in:

- `docs/superpowers/specs/2026-06-23-production-infrastructure-maturity-design.md`
- `docs/superpowers/plans/2026-06-23-production-infrastructure-maturity.md`

Current remaining focus:

1. Keep `just check` green locally.
2. Keep frontend i18n lint and generated client freshness passing.
3. Keep `just install-agent` and `just doctor` reliable on Windows.
4. Treat unexpected Alembic readiness probe failures as not ready.
5. Keep this document as historical context unless it is fully rewritten.

---

## 1. Executive Summary

EKONT SMART REPORT has a strong foundation: a FastAPI backend, React/Vite frontend, agent-native CLI, shared `scada-core` package, TimescaleDB/Alembic infrastructure, Prometheus metrics, multilingual frontend, Docker services, and GitHub Actions CI.

The current review confirms that several previously identified risks are still valid:

- Python package version requirements are inconsistent.
- Production configuration validation currently checks only the default JWT secret.
- Backend startup still runs `Base.metadata.create_all()`.
- The API process starts the collector by default.
- SSE endpoints pass the token through the query string.
- The frontend contains both `package-lock.json` and `pnpm-lock.yaml`, while CI and `justfile` use pnpm.
- Backend runtime and dev/test dependencies are combined in one `requirements.txt`.
- Root `just check` exists, but it does not cover frontend, CLI, MCP, and security checks.
- Additional gaps exist around reproducible Python locks, OAuth2 form-data login ergonomics, seed script imports, test isolation, MCP CI, PLC alerting, backup/restore documentation, and Grafana dashboard provisioning.

The document now separates confirmed repository evidence from recommended changes so the roadmap can be converted into implementation tickets without another discovery pass.

Highest-priority recommendations:

| Priority | Recommendation | Why It Matters |
|---|---|---|
| Critical | Align Python version requirements | CLI, backend, and `scada-core` should install cleanly with one supported Python version. |
| Critical | Expand production secret and credential validation | Default DB, Grafana, and seed credentials must not reach production. |
| High | Use Alembic, not `create_all()`, as the production schema authority | Reduces schema drift and missing migration risk. |
| High | Separate the collector from API workers by default | Prevents PLC acquisition from multiplying when API workers scale. |
| High | Remove SSE query-token authentication | Prevents JWT leakage through logs, browser history, and proxy traces. |
| Medium | Standardize the frontend on pnpm | CI already uses pnpm; dual lockfiles create dependency drift. |
| Medium | Align `just check` with CI | The local quality gate should match CI behavior. |
| Medium | Wire OpenAPI client generation into build/CI | Reduces backend/frontend contract drift. |

---

## 2. Current Project Shape

Main components:

- `scada-reporter/backend/`: FastAPI application, SQLAlchemy models, Alembic migrations, collector, scheduler, reporting services, and tests.
- `scada-reporter/frontend/`: React 19 + Vite frontend, Vitest/Playwright setup, i18n resources, RTL checks, and OpenAPI client generation config.
- `scada-reporter/agent-harness/`: Click-based agent CLI exposing the `scada` / `scada-reporter` commands.
- `scada-reporter/packages/scada-core/`: Shared catalog, client, and formatting primitives for agent-facing tools.
- `mcp-servers/`: MCP server experiments for SCADA and database access.
- `.github/workflows/ci.yml`: CI for backend, CLI, and frontend.
- `justfile`: Development, test, migration, frontend, and agent commands.
- `scada-reporter/docker/`: TimescaleDB, Redis, Grafana, and Portainer services.

The agent-native structure is now clear. The next most valuable work is to make production behavior explicit and safe without losing local development convenience.

---

## 3. Verified Repository Evidence

The following evidence was checked in the current tree before updating these recommendations:

| Area | Verified Evidence | Current Implication |
|---|---|---|
| Python versions | `scada-core` requires Python `>=3.14`; CLI declares `>=3.11`; backend and CI target Python `3.12`. | Package metadata is inconsistent and can break editable installs or CI smoke tests. |
| Production config | `Settings.config_errors()` only rejects the default `SECRET_KEY` in production. | Other dangerous defaults can still pass production startup. |
| Schema startup | `app/main.py` runs `Base.metadata.create_all()` during lifespan startup. | Production has two schema paths: ORM startup creation and Alembic migrations. |
| Collector runtime | `RUN_COLLECTOR=True` by default; API lifespan starts poller and OPC UA server. | Scaling API workers can multiply PLC polling unless deployments override the setting. |
| SSE auth | Frontend `EventSource` streams include `token` in the URL; backend supports query-token validation. | Long-lived JWTs can leak through URL-based logs and traces. |
| Frontend package manager | `package-lock.json` and `pnpm-lock.yaml` both exist; `justfile`, CI, and frontend docs use pnpm. | pnpm is the de facto standard, but the extra npm lockfile creates ambiguity. |
| OpenAPI client | OpenAPI generation config and scripts exist, but `src/api/generated/` is absent and `src/api/client.ts` is handwritten. | Generated clients are planned but not yet the active contract source. |
| Quality gate | Root `just check` exists and covers backend lint/format/type/test only. | Local checks do not match CI, which also covers frontend, CLI, and Bandit. |
| CI reproducibility | Frontend CI uses `pnpm install`; backend CI installs dev tools ad hoc next to `requirements.txt`. | CI is useful but dependency resolution is not fully pinned or grouped. |
| Runtime observability | `/health` and `/metrics` exist; collector metrics cover tick/read/write/bad-quality signals. | Metrics are a good base, but liveness/readiness separation is still missing. |
| Auth ergonomics | `/api/auth/token` uses `OAuth2PasswordRequestForm`; no JSON login wrapper is present. | API consumers can easily send JSON and fail unless the form-data requirement is documented or wrapped. |
| Python lockfiles | No `requirements.lock` or `uv.lock` is present. | Backend installs use open-ended constraints and can resolve differently over time. |
| Docker app images | No backend/frontend Dockerfile was found; compose currently contains infrastructure services only. | Production-like container topology is not yet represented in the repository. |
| Seed scripts | Seed scripts such as `seed_users.py` use `sys.path.insert(...)`. | Script execution depends on path hacks instead of installed package/module execution. |
| Test isolation | Backend tests use in-memory SQLite with `StaticPool` and table deletion between tests. | Isolation works pragmatically, but it is weaker than transactional rollback or PostgreSQL-backed tests. |
| MCP CI | `mcp-servers/mcp-scada/pyproject.toml` exists, but `.github/workflows/ci.yml` has no MCP job. | MCP code can drift outside the main quality gate. |
| Grafana dashboards | Grafana datasource provisioning exists, but no dashboard provisioning files were found. | Operators do not get version-controlled dashboards by default. |
| Local artifacts | `.gitignore` covers many artifacts, but untracked local/generated files and folders are present. | Artifact policy needs tightening to reduce accidental commits. |

## 4. Immediate Implementation Order

If the team wants to turn this document into work items, the lowest-risk, highest-signal order is:

1. Align Python metadata to Python 3.12 across backend, CLI, and `scada-core`.
2. Standardize frontend package management on pnpm and remove `package-lock.json`.
3. Split backend runtime dependencies from dev/test/security dependencies.
4. Add reproducible dependency locks for backend installs.
5. Expand `just check` so local checks match the existing CI jobs.
6. Change CI installs to reproducible modes, especially `pnpm install --frozen-lockfile`.
7. Expand production configuration validation for known unsafe defaults.
8. Make `create_all()` and `RUN_COLLECTOR` safe by default for production deployments.
9. Replace query-string JWTs in SSE with a short-lived stream token or another safer auth model.
10. Add the missing operational guides and dashboards after runtime behavior is stable.

This sequence avoids deep runtime changes until the repository baseline, dependency workflow, and quality gate are stable.

## 5. Findings and Recommendations

### 5.1 Align Python Version Requirements

**Current state**

- `scada-reporter/packages/scada-core/pyproject.toml`: `requires-python = ">=3.14"`
- `scada-reporter/agent-harness/setup.py`: `python_requires=">=3.11"`
- `scada-reporter/backend/pyproject.toml`: `target-version = "py312"` and `python_version = "3.12"`
- `.github/workflows/ci.yml`: uses Python `3.12` for backend and CLI jobs.

**Risk**

If the agent CLI is installed editable together with `scada-core`, package metadata can conflict in the Python 3.12 CI environment. The code may be compatible, but installation can still fail because `scada-core` declares Python 3.14+.

**Recommendation**

Use Python 3.12 as the single supported baseline:

- Set `scada-core` to `requires-python = ">=3.12"`.
- Set the CLI to `python_requires=">=3.12"` if Python 3.11 is not explicitly supported and tested.
- Document the Python 3.12 requirement in the root `README.md`, `AGENTS.md`, or setup section.
- Add a CI smoke test that installs backend, CLI, and `scada-core` in editable mode.

**Success criteria**

A fresh checkout can install backend, CLI, and core packages with one documented Python version.

---

### 5.2 Expand Production Configuration and Secret Validation

**Current state**

`Settings.config_errors()` currently catches only the default `SECRET_KEY` in production.

Development assumptions still exist in the repository:

- `DATABASE_URL=postgresql+asyncpg://scada:scada123@localhost:5432/scada_reporter`
- Docker DB password: `scada123`
- Grafana admin password: `admin`
- Seed users: `admin/admin123`, `operator/operator123`
- `RUN_COLLECTOR=True`
- Development CORS origins

**Risk**

These values are useful for local demos, but they become direct security risks if copied into staging or production.

**Recommendation**

Expand production validation to cover:

- Default `SECRET_KEY`
- Default database password or local demo DSN
- Empty, wildcard, or localhost-only `CORS_ORIGINS`
- `RUN_COLLECTOR=True` for API deployments
- Known seed credentials
- Grafana default admin credentials

Also:

- Keep `.env.example` development-friendly.
- Add `.env.production.example` with placeholders.
- Fail startup in production with clear error messages.
- Document secret generation commands.

**Success criteria**

The application refuses to start with unsafe defaults under `ENVIRONMENT=production`.

---

### 5.3 Use Alembic as the Production Schema Authority

**Current state**

`scada-reporter/backend/app/main.py` runs the following during startup:

- `Base.metadata.create_all()`
- TimescaleDB initialization
- Continuous aggregate initialization

Alembic migration files also exist and are actively used.

**Risk**

`create_all()` can hide missing migrations in production. Having both ORM startup schema creation and Alembic as schema paths increases schema drift risk.

**Recommendation**

Make schema behavior environment-specific:

- Development: optionally allow `AUTO_CREATE_TABLES=True` for fast setup.
- Staging/production: keep `AUTO_CREATE_TABLES=False`; require `alembic upgrade head` before deployment.
- Add a readiness check that verifies the database is at the expected Alembic head.

**Success criteria**

Production schema changes are applied only through Alembic migrations.

---

### 5.4 Separate Collector Runtime from API Runtime

**Current state**

`RUN_COLLECTOR=True` is the default. `main.py` starts the S7 poller and OPC UA server inside the API lifespan. A separate collector entrypoint already exists:

- `python -m app.collector.runner`
- `just run-collector`

**Risk**

If the API runs with multiple workers or replicas, every worker can start PLC acquisition. That can cause duplicate reads/writes, extra PLC load, and hard-to-debug timing issues.

**Recommendation**

Make the production topology explicit:

- API process: serves HTTP and does not start the collector.
- Collector process: owns PLC polling and database writes.
- OPC UA, if needed, is owned by either a separate process or the collector role.

Practical changes:

- Set `RUN_COLLECTOR=False` in API deployment environments.
- Add Docker Compose profiles or services for `api`, `collector`, `frontend`, and optionally `scheduler`.
- Document which service owns PLC polling.

**Success criteria**

Increasing API worker count does not increase PLC acquisition count.

---

### 5.5 Secure SSE Authentication

**Current state**

Frontend `EventSource` calls pass the token in the query string:

- `/api/dashboard/stream?...&token=...`
- `/api/dashboard/logs/stream?...&token=...`

The backend supports query-token validation because native EventSource cannot send headers.

**Risk**

Long-lived JWTs in URLs can leak through browser history, reverse proxy access logs, server logs, error reporting tools, or screenshots.

**Recommendation**

Use one of these patterns:

1. Short-lived SSE token: the client requests a scoped stream token over normal authenticated HTTP, then uses that token only for SSE.
2. Secure HTTP-only cookie: move auth to cookies so EventSource sends credentials automatically.
3. Fetch-based streaming: replace native EventSource with streaming `fetch`, which can send an `Authorization` header.

For the current architecture, short-lived SSE tokens are likely the smallest change.

**Success criteria**

Long-lived JWTs no longer appear in URLs, and stream reconnection still works.

---

### 5.6 Add a JSON Login Wrapper or Document OAuth2 Form Login Clearly

**Current state**

`/api/auth/token` uses FastAPI's `OAuth2PasswordRequestForm`, so clients must send `application/x-www-form-urlencoded` form data. There is no visible JSON login endpoint such as `/api/auth/login`.

**Risk**

Most frontend and integration clients expect JSON APIs. Sending `{"username": "...", "password": "..."}` to the token endpoint will fail, which creates avoidable integration friction.

**Recommendation**

- Add `/api/auth/login` that accepts JSON credentials and delegates to the same token creation logic.
- Keep `/api/auth/token` for OAuth2 compatibility.
- Document the form-data requirement in OpenAPI/client docs if the JSON wrapper is deferred.

**Success criteria**

Human and agent consumers can authenticate without knowing OAuth2 form encoding details, while OAuth2-compatible clients still work.

---

### 5.7 Standardize Frontend Package Management on pnpm

**Current state**

`scada-reporter/frontend/` contains two lockfiles:

- `package-lock.json`
- `pnpm-lock.yaml`

However:

- `justfile` uses `pnpm` for frontend commands.
- GitHub Actions uses `pnpm/action-setup` and caches `pnpm-lock.yaml`.
- `frontend/README.md` documents pnpm commands.

**Risk**

Two lockfiles can represent different dependency graphs. This creates local/CI drift and weakens reproducible builds.

**Recommendation**

Make pnpm the official package manager:

- Remove `package-lock.json`.
- Use `pnpm install --frozen-lockfile` in CI.
- Document pnpm as the required frontend package manager in root documentation.

**Success criteria**

The frontend has one lockfile, and local/CI installs use the same package manager.

---

### 5.8 Make the OpenAPI Client the Real Contract Source

**Current state**

OpenAPI client generation is configured:

- `scada-reporter/frontend/openapi-ts.config.ts`
- `package.json`: `gen-client`
- `justfile`: `gen-client`

But `src/api/generated/` is not present; active API usage is mostly through handwritten `src/api/client.ts`.

**Risk**

Frontend types and endpoint contracts can drift as backend schemas evolve.

**Recommendation**

Migrate gradually:

- Generate the client into `src/api/generated/`.
- Keep handwritten `client.ts` only for auth, axios setup, and ergonomic wrappers.
- Use generated request/response types instead of duplicated manual interfaces.
- In CI, start the backend, run `pnpm gen-client`, and fail if generated output is stale.

**Success criteria**

Backend OpenAPI changes become visible through frontend build or generated-client freshness checks.

---

### 5.9 Strengthen RBAC and Authentication Boundaries

**Current state**

Permission checks and tests exist. Protections also prevent deleting, deactivating, or demoting the last active admin. However, role fields are mostly plain strings:

- `User.role: String(50)`
- API schemas use `role: str`
- No visible DB-level role check constraint

**Risk**

Invalid role values can enter the API or database layer. The permission system denies unknown roles, but data quality and admin workflows still become ambiguous.

**Recommendation**

- Use `Literal["admin", "operator", "viewer"]` in API schemas.
- Add a database check constraint for role values through a migration.
- Use a frontend union type for role values.
- Add login rate limiting.
- Add audit logging for admin actions such as password reset, role change, user deletion, and user deactivation.
- Consider token versioning so password reset can invalidate old tokens.

**Success criteria**

Invalid role values are rejected at API and DB boundaries, and sensitive admin actions are auditable.

---

### 5.10 Clarify Health, Readiness, and Metrics

**Current state**

Existing endpoints:

- `/health`: returns process and PLC connection summary.
- `/metrics`: returns Prometheus metrics.

Existing collector metrics:

- Tick duration
- PLC read duration
- Rows written
- Bad quality count
- Metrics summary helper for dashboard usage

**Risk**

A single `/health` endpoint cannot answer both:

- Is the process alive?
- Is the service ready to receive traffic?

Database, Redis, migration level, scheduler, and collector state should be evaluated separately for readiness.

**Recommendation**

Split endpoints:

- `/live`: event loop/process is alive.
- `/ready`: database reachable, Alembic head current, Redis reachable if required, scheduler state valid.
- `/health`: human-readable summary including PLC and collector information.

Keep the existing collector metrics and add:

- HTTP request latency/error count
- DB pool usage
- Scheduler job success/failure
- Latest-value cache age
- Redis connection state, if Redis is required

**Success criteria**

The orchestrator can make separate liveness/readiness decisions, and operators can tell whether an issue is API, DB, collector, scheduler, or PLC-side.

---

### 5.11 Separate Backend Dependency Groups

**Current state**

`scada-reporter/backend/requirements.txt` contains runtime and dev/test dependencies together. It has a `# Dev/test` section, but production installs still include pytest, coverage, and test tools if they use the same file.

**Risk**

Production images become larger and include unnecessary packages, increasing attack surface.

**Recommendation**

Choose one of these patterns:

- `requirements.txt`: runtime only
- `requirements-dev.txt`: test/lint/type/security tools

or:

- `pyproject.toml` for runtime dependencies
- `[project.optional-dependencies.dev]` for dev/test tools

Short term, two requirements files are the lowest-risk change.

**Success criteria**

Production installs runtime dependencies only; CI installs dev/test dependencies explicitly.

---

### 5.12 Add Reproducible Python Dependency Locks

**Current state**

Backend dependencies use broad `>=` constraints in `requirements.txt`, and no `requirements.lock` or `uv.lock` file is present.

**Risk**

Two installs at different times can resolve different transitive dependency versions. This can cause CI, development, and production drift.

**Recommendation**

Use a lock or sync workflow:

```bash
cd scada-reporter/backend
uv pip compile requirements.txt -o requirements.lock
uv pip sync requirements.lock
```

If the project moves toward a package-based backend, prefer a `pyproject.toml` plus `uv.lock` workflow.

**Success criteria**

Backend CI and deployment installs resolve the same dependency graph from a committed lockfile.

---

### 5.13 Align the Local Quality Gate with CI

**Current state**

The root `justfile` has:

```bash
just check
```

Current scope:

- Backend lint
- Backend format-check
- Backend mypy
- Backend pytest

CI additionally runs:

- Backend Bandit security scan
- Agent CLI tests
- Frontend TypeScript check, lint, and Vitest

**Risk**

A change can pass `just check` locally but fail in CI on frontend, CLI, or security steps.

**Recommendation**

Expand `just check` to match CI:

- Backend: `lint`, `format-check`, `typecheck`, `test`, and ideally `security`
- Frontend: `pnpm tsc --noEmit`, `pnpm lint`, `pnpm test`, and optionally `pnpm build`
- CLI: `just test-agent`
- Generated client freshness: separate command or part of check
- MCP: `mcp-check` once the MCP test flow is standardized

Suggested commands:

```bash
just backend-check
just frontend-check
just cli-check
just mcp-check
just check
```

**Success criteria**

The single recommended pre-PR command is as close as practical to CI behavior.

---

### 5.14 Make CI Installs More Reproducible

**Current state**

CI exists and is useful. However, the frontend install step uses `pnpm install` without strict lockfile enforcement. The backend job installs `ruff mypy bandit safety` directly alongside `requirements.txt`.

**Risk**

CI dependency resolution can change over time. This is especially true for Python dev tools and Node package graphs.

**Recommendation**

- Frontend CI: use `pnpm install --frozen-lockfile`.
- Backend: move dev dependencies into `requirements-dev.txt` or `pyproject` optional dependencies.
- CLI: add a smoke test for editable `scada-core` dependency installation.
- Add an OpenAPI generation freshness job.
- MCP: add a minimal `mcp-scada` install/import/test job.

**Success criteria**

CI dependency graphs are repeatable through lockfiles and explicit dependency groups.

---

### 5.15 Improve Seed Scripts, Test Isolation, and Coverage

**Current state**

Seed scripts such as `seed_users.py` use `sys.path.insert(...)` for import resolution. Backend tests use SQLite in-memory with `StaticPool` and clear tables between tests instead of using transaction rollback. Test coverage exists broadly, but several operational paths are still higher risk.

**Risk**

Path hacks make scripts fragile outside the current working-directory assumptions. Table deletion isolation is pragmatic but can miss transaction-specific behavior. Untested seed, collector, and frontend mutation paths can regress silently.

**Recommendation**

- Install the backend package in editable mode for development/test scripts.
- Run seed scripts as modules, for example `python -m app.seed_users`.
- Add a `just seed` command that runs seed scripts in the documented order.
- Replace `sys.path.insert(...)` usage once module execution is reliable.
- Consider transactional test rollback, or PostgreSQL/Testcontainers for database behavior closer to production.
- Add `pytest-timeout` to avoid hanging async tests.
- Add focused coverage for seed `main()` functions, collector disconnection/timeouts, bad-quality data handling, and frontend mutation functions.
- Add a CI coverage step with an agreed threshold once the baseline is measured.

**Success criteria**

Seed scripts run from installed package context, database tests are isolated predictably, and CI protects the highest-risk runtime paths.

---

### 5.16 Add MCP Server CI Coverage

**Current state**

`mcp-servers/mcp-scada/pyproject.toml` and tests exist, but the GitHub Actions workflow does not include an MCP job.

**Risk**

MCP server code can break independently of backend/frontend/CLI checks.

**Recommendation**

- Add `just mcp-check`.
- Add a CI job that installs `mcp-servers/mcp-scada` in editable mode.
- Run import smoke tests and the MCP test suite.

**Success criteria**

MCP server changes are validated in the same quality gate as the rest of the repository.

---

### 5.17 Add PLC Connection Monitoring and Operator Alerts

**Current state**

`/health` exposes PLC connection counts, and Prometheus metrics include collector timing/quality signals. There is no documented operator alert path for PLC offline/recovery events.

**Risk**

Operators may only discover PLC disconnection through manual dashboard inspection or downstream data gaps.

**Recommendation**

- Track PLC connection loss/recovery events in a `PlcConnectionLog`-style model or event store.
- Show PLC connection state and last successful read timestamp in the dashboard.
- Emit frontend notifications for connection loss/recovery.
- Optionally add email or webhook notifications for production deployments.
- Track reconnection attempts and time since last successful read.

**Success criteria**

PLC connectivity problems are visible to operators without manually polling the health endpoint.

---

### 5.18 Document Backup, Restore, and Disaster Recovery

**Current state**

No dedicated backup/restore guide was found for TimescaleDB data, configuration, report archives, or deployment recovery.

**Risk**

Operational recovery depends on implicit knowledge. This is risky for SCADA reporting data, long-term tag history, and environment-specific configuration.

**Recommendation**

Create `docs/backup-recovery.md` covering:

- PostgreSQL/TimescaleDB backup strategy.
- Metadata/schema dumps and time-series data backups.
- Report archive backup and retention.
- `.env`, Docker, Alembic, and Grafana provisioning backup.
- Step-by-step restore procedure.
- Automated backup script and retention policy.

**Success criteria**

An operator can restore the application and data from documented steps without relying on the original developer.

---

### 5.19 Provision Grafana Dashboards

**Current state**

Grafana datasource provisioning exists under `scada-reporter/docker/grafana/datasources/`, but no dashboard JSON provisioning files were found.

**Risk**

Operators must build dashboards manually, and monitoring views are not version-controlled.

**Recommendation**

- Add Grafana dashboard provisioning under `scada-reporter/docker/grafana/dashboards/`.
- Commit dashboards for PLC connection state, read latency, collector tick duration, rows written, bad-quality ratio, API request rate, error rate, and latency.
- Keep dashboards aligned with Prometheus metric names.

**Success criteria**

Grafana starts with useful version-controlled dashboards for SCADA and API operations.

---

### 5.20 Consolidate Agent Documentation

**Current state**

Agent guidance exists at both root `AGENTS.md` and `scada-reporter/AGENTS.md`.

**Risk**

Duplicated agent instructions can drift, especially as CLI commands, plugin structure, and setup steps change.

**Recommendation**

- Keep one authoritative `AGENTS.md` entry point.
- Make the secondary file a short redirect or scoped supplement.
- Put detailed guides under `scada-reporter/guides/` or `docs/`.

**Success criteria**

Agent setup and usage instructions have one clear source of truth.

---

### 5.21 Update Generated and Local Artifact Policy

**Current state**

`.gitignore` already covers many local folders and runtime artifacts. At the time of
the original review, the working tree showed local/generated or untracked areas such
as:

- `xlsx/`
- `docs/recommend.md`
- `docs/superpowers/plans/...`
- `.claude/worktrees/`
- `.commit_msg.txt`
- `cld.bat`

**Risk**

Generated or local work files can be committed accidentally, causing noisy diffs, repository growth, or sensitive data exposure.

**Recommendation**

- Decide whether `xlsx/` is sample input data or local-only input.
- Add ignore rules for Office lock files such as `~$*.docx` and `~$*.xlsx`.
- Document when exported PDF/HTML/XLSX artifacts should be tracked.
- Add local agent workspaces such as `.claude/worktrees/` to ignore rules.
- For intentionally tracked document outputs, distinguish source files from deliverables.

**Success criteria**

After normal development workflows, `git status` shows only intentional source changes.

---

### 5.22 Separate Local Docker Infrastructure from Production Topology

**Current state**

`scada-reporter/docker/docker-compose.yml` provides local infrastructure services:

- TimescaleDB
- Redis
- Grafana
- Portainer

API, collector, and frontend do not appear as separate production-like services in this compose file. No backend/frontend Dockerfiles were found in the repository scan. DB and Grafana credentials use development defaults.

**Risk**

If the local convenience compose file is used as a production deployment template, it carries both credential and topology risks.

**Recommendation**

- Label the current compose file clearly as local/dev infrastructure.
- Add backend and frontend Dockerfiles when containerized deployment becomes a supported path.
- Prepare a separate staging/production compose file or deployment guide.
- Consider adding API, collector, and frontend services as separate profiles.
- Require environment overrides for Grafana admin password and DB password.
- Use health/readiness endpoints in service healthchecks once they exist.
- Create a `DOCKER.md` guide for local infrastructure, production-like topology, and required host prerequisites.

**Success criteria**

Local compose usage and production deployment responsibilities are not confused.

---

## 6. Suggested Roadmap

### Phase 1 - Low-Risk Alignment

- Align Python version metadata around 3.12.
- Make pnpm the single frontend package manager and remove `package-lock.json`.
- Split backend runtime and dev/test dependencies.
- Add backend dependency locks with `requirements.lock` or `uv.lock`.
- Expand `just check` to include frontend and CLI checks.
- Use frozen/reproducible installs in CI.
- Add MCP smoke/test coverage to CI.

### Phase 2 - Production Safety

- Expand production configuration validation.
- Add `.env.production.example`.
- Make startup `create_all()` behavior environment-specific.
- Separate API and collector runtimes at deployment level.
- Add a JSON login wrapper or document OAuth2 form login prominently.
- Document Docker local vs production usage.
- Remove seed script path hacks and standardize module-based seed execution.

### Phase 3 - Auth, Contract, and Operations

- Replace SSE query-token authentication.
- Add RBAC role types and database constraints.
- Add admin audit logging and login rate limiting.
- Gradually adopt the generated OpenAPI client.
- Implement `/live`, `/ready`, and `/health` separation.
- Add PLC connection monitoring and operator-facing alerts.
- Improve async test isolation and add coverage for seed, collector, and frontend mutation paths.

### Phase 4 - Operational Maturity

- Add backup/restore guidance.
- Connect TimescaleDB retention and rollup policy to deployment documentation.
- Standardize Grafana/Prometheus dashboards.
- Add backend/frontend Dockerfiles if containerized app deployment is supported.
- Consolidate agent documentation into a single source of truth.
- Define release notes and versioning policy for backend, frontend, CLI, and `scada-core`.

---

## 7. Acceptance Checklist

- [ ] Python versions are aligned across backend, CLI, `scada-core`, and CI.
- [ ] A CI smoke test installs backend, CLI, and `scada-core` together.
- [ ] Production startup rejects unsafe default secrets and credentials.
- [ ] `create_all()` does not run in production; Alembic is the only schema path.
- [ ] API and collector run as separate production processes/services.
- [ ] SSE streams no longer expose long-lived JWTs in query strings.
- [ ] Frontend has one lockfile: `pnpm-lock.yaml`.
- [ ] Frontend CI uses `pnpm install --frozen-lockfile`.
- [ ] Backend runtime and dev/test dependencies are separated.
- [ ] Backend installs use a committed dependency lockfile.
- [ ] `just check` covers backend, frontend, and CLI checks.
- [ ] CI and the local quality gate are aligned.
- [ ] MCP server install/import/tests run in CI.
- [ ] `/live`, `/ready`, and `/health` endpoints are separated.
- [ ] RBAC role values are constrained by API schemas and database rules.
- [ ] Admin actions are written to an audit log.
- [ ] Login endpoint has rate limiting.
- [ ] JSON login or clearly documented form-data login is available.
- [ ] Generated OpenAPI client usage or freshness checks are active.
- [ ] Seed scripts run without `sys.path` import hacks.
- [ ] Test coverage has a measured baseline and agreed threshold.
- [ ] PLC connection state is visible to operators with alerting or notifications.
- [ ] Backup/restore procedure is documented.
- [ ] Grafana dashboards are version-controlled and provisioned.
- [ ] Docker application deployment path is documented if supported.
- [ ] Agent documentation has one authoritative entry point.
- [ ] Local/generated artifact policy is clear in `.gitignore` and documentation.

---

## 8. Final Notes

The project does not need a broad rewrite. The current architecture is modular enough for incremental hardening. The highest-value work is to keep development convenient while making production behavior explicit: one Python baseline, one frontend package manager, reproducible dependency installs, separate API/collector topology, Alembic-centered schema management, safe secret policy, operator-visible monitoring, documented recovery, and a local quality gate that matches CI.
