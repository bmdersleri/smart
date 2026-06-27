# Production Infrastructure Maturity — Design Spec

**Date:** 2026-06-23
**Status:** Proposed
**Scope:** Infrastructure additions that improve releaseability, field operations, backup confidence, observability, configuration safety, and production-like verification. This spec does not change product features or the supported process-based deployment model.

## 1. Goal

Make EKONT SMART REPORT easier to ship, install, operate, diagnose, and recover in real plant environments while preserving the repository's explicit architecture decisions:

- The application runs as native host processes in production.
- Docker Compose is for local infrastructure only.
- The collector is a single dedicated process.
- Alembic remains the production schema authority.
- `just check` remains the local CI-equivalent quality gate.
- Agent CLI and MCP surfaces remain first-class, stable interfaces.

The target outcome is an operator- and maintainer-friendly infrastructure layer:

- A tagged release produces usable artifacts.
- Windows service installation is repeatable.
- Backups are not only documented but restore-tested.
- Prometheus/Grafana emits actionable alerts, not only dashboards.
- A production-like smoke test catches topology and contract issues before release.
- Configuration and dependency risks are detected automatically.

## 2. Current State

The repository already has a strong baseline:

- Backend: FastAPI, SQLAlchemy 2.0, Alembic, tests, Bandit, mypy, ruff.
- Frontend: React/Vite, pnpm, TypeScript, ESLint, Vitest, Playwright config, generated OpenAPI client.
- Agent surfaces: Click-based CLI, shared `scada-core`, MCP server tests.
- Local infrastructure: TimescaleDB, Redis, Prometheus, optional Grafana profile, Portainer.
- Deployment docs: process-based production topology with API, collector, and frontend separated.
- Operational docs: backup/restore runbook, Grafana provisioning docs, Docker local-infra guide.
- CI: backend, frontend, CLI, MCP, and OpenAPI contract freshness.
- Local gate: `just check` covers backend/frontend/CLI/MCP/contract checks.
- Doctor script: basic Windows development environment diagnostics.

Remaining infrastructure gaps are not foundation gaps; they are maturity gaps:

- Releases create GitHub Release notes but do not yet attach installable artifacts.
- Windows service scripts exist for selected components but the full API/collector/frontend service lifecycle is not unified.
- Backup guidance exists, but there is no automated restore smoke test.
- Prometheus/Grafana exist, but alert rules and Alertmanager routing are not provisioned.
- There is no single production-like smoke command that validates DB migrations, API readiness, collector simulation, frontend build, CLI, and MCP together.
- Security scanning exists for Python code but supply-chain and SBOM checks are not yet part of the infrastructure gate.
- `doctor.ps1` checks common prerequisites but does not yet perform deeper configuration and credential safety checks.

## 3. Non-Goals

- Do not add production Dockerfiles or production Compose files unless the project reverses the documented process-based deployment decision.
- Do not move application runtime into Docker.
- Do not redesign application features such as reports, dashboards, PLC health, or licensing.
- Do not replace Alembic with ORM auto-creation in production.
- Do not make Grafana the source of truth for business data.
- Do not require cloud-specific infrastructure such as AWS, Azure, or GCP.
- Do not introduce Kubernetes as a required runtime.

## 4. Design Principles

| Principle | Implication |
|---|---|
| Process-based production remains authoritative | Service management should target native OS process supervisors, especially Windows services and systemd-compatible docs/scripts. |
| Release artifacts should be installable | A Git tag should produce backend/CLI Python artifacts, frontend static assets, checksums, and operator-facing notes. |
| Recovery must be rehearsed | Backup docs are necessary but insufficient; a restore smoke test should prove that the latest backup can boot a minimal restored environment. |
| Alerts should be actionable | Alert rules must point to conditions operators can respond to: PLC offline, stale reads, DB readiness, disk capacity, report failures, and collector liveness. |
| Local and CI should agree | New infrastructure checks should be available through `just` recipes and mirrored in CI only after they are deterministic. |
| Agent surfaces are contracts | CLI JSON output, MCP resources/tools, and `SKILL.md` should be protected against accidental drift. |
| Security checks should be staged | Add SBOM/audit/config gates in report-only or narrowly scoped mode first, then promote to blocking once noise is understood. |

## 5. Proposed Architecture

### 5.1 Release Artifact Pipeline

Add a release build workflow that runs on version tags and produces a complete release bundle:

- Backend runtime dependency lock metadata.
- Python wheel/sdist for `scada-core`.
- Python wheel/sdist for `scada-reporter-cli`.
- Optional backend source archive with pinned runtime lock file.
- Frontend `dist/` zip generated from `pnpm install --frozen-lockfile && pnpm build`.
- OpenAPI schema snapshot.
- Generated TypeScript client checksum or manifest.
- `CHANGELOG.md` section extracted for the tag.
- SHA256 checksums for all artifacts.
- Optional SBOM files for Python and frontend dependencies.

The existing GitHub Release workflow remains the publishing mechanism. This change extends it from "release notes only" to "release notes plus artifacts".

#### Artifact Naming

Use deterministic names:

- `ekont-smart-report-backend-source-vX.Y.Z.zip`
- `ekont-smart-report-frontend-dist-vX.Y.Z.zip`
- `scada-core-vX.Y.Z-py3-none-any.whl`
- `scada-reporter-cli-vX.Y.Z-py3-none-any.whl`
- `openapi-vX.Y.Z.json`
- `checksums-vX.Y.Z.sha256`
- `sbom-python-vX.Y.Z.json`
- `sbom-frontend-vX.Y.Z.json`

#### Version Consistency

A release validation script should verify:

- Git tag version matches `CHANGELOG.md` heading.
- CLI/core/backend/frontend version fields are either equal or intentionally mapped.
- OpenAPI/generated client is fresh.
- `just check` passes before artifact packaging.

### 5.2 Native Service Lifecycle

Add a unified Windows service management layer for production processes:

- API service.
- Collector service.
- Frontend static file service.
- Optional Grafana service integration status.
- Optional Prometheus service integration status.

The service layer should provide:

- Install.
- Uninstall.
- Start.
- Stop.
- Restart.
- Status.
- Log path discovery.
- Environment file path discovery.

Recommended commands:

- `just install-services`
- `just uninstall-services`
- `just start-services`
- `just stop-services`
- `just restart-services`
- `just service-status`

Scripts should be idempotent where practical and should fail with clear messages when prerequisites are missing.

#### Service Environment Split

The API service must run with:

```env
RUN_COLLECTOR=False
```

The collector service must run with:

```env
RUN_COLLECTOR=True
```

The service installer should warn or fail if both services point to an environment file that would start the collector in the API process.

### 5.3 Backup Restore Smoke Test

Add an automated restore verification flow that proves a backup can be restored into a temporary database and inspected.

The smoke test should support at least:

- Latest backup file discovery.
- Explicit backup file input.
- Temporary database name or isolated container volume.
- `pg_restore` or `psql` restore depending on backup format.
- Alembic `current` and `upgrade head`.
- Basic table existence checks.
- Count checks for critical tables.
- Optional API `/ready` check against the restored database.

Recommended commands:

- `just backup-db`
- `just restore-smoke`
- `just restore-smoke backup="path/to/file.dump"`

The restore smoke test should be non-destructive and must never run against the configured production database unless explicitly passed a dedicated restore target.

### 5.4 Observability and Alerting

Prometheus and Grafana are already present. Add alerting infrastructure:

- Prometheus alert rules under version control.
- Optional Alertmanager service/config for local and production operations.
- Grafana dashboard panels aligned with alert signals.
- Runbook links in alert annotations.

Initial alert categories:

| Category | Alert | Trigger |
|---|---|---|
| API | API not ready | `/ready` reports not ready or scrape fails. |
| API | High 5xx rate | Error ratio crosses threshold for sustained window. |
| API | High latency | Request latency p95 exceeds threshold. |
| Collector | Collector stale | No collector tick/read metric update for threshold duration. |
| PLC | PLC offline | PLC health reports disconnected/open critical incident. |
| PLC | Stale readings | Latest successful reading age exceeds threshold. |
| Database | DB not ready | Readiness DB or Alembic check fails. |
| Reports | Report generation failures | Failure counter increases. |
| Disk | Backup/report disk low | Free disk below threshold where metric is available. |
| Security | Login failures spike | Login rate-limit or failure counter crosses threshold. |

Alert rules should start conservative to avoid noise. Use labels and annotations:

- `severity`
- `component`
- `summary`
- `description`
- `runbook_url`

### 5.5 Production-Like Smoke Test

Add a deterministic smoke command that exercises the real topology without requiring a real PLC:

1. Start local infrastructure or assert it is already running.
2. Apply Alembic migrations.
3. Seed required users.
4. Start API with `RUN_COLLECTOR=False`.
5. Start collector with `RUN_COLLECTOR=True` in simulation-safe mode.
6. Check `/live`, `/ready`, `/health`, and `/metrics`.
7. Build frontend.
8. Run a minimal Playwright or HTTP smoke against the served frontend if feasible.
9. Install or invoke the agent CLI.
10. Run CLI health/tags/dashboard commands with JSON output.
11. Run MCP import/resource smoke tests.

Recommended commands:

- `just smoke-prodlike`
- `just smoke-prodlike-fast`

The fast variant may skip frontend e2e and long-running collector checks, but must still validate migrations, readiness, CLI JSON, and OpenAPI freshness.

### 5.6 Supply-Chain and License Controls

Add infrastructure checks that produce actionable reports:

- Python dependency vulnerability audit.
- Frontend dependency audit.
- SBOM generation.
- License policy report.
- GitHub CodeQL or equivalent static analysis.
- Trivy/Grype scan for local infrastructure images if image scanning is useful for the deployment context.

Recommended staging:

1. Add report generation commands.
2. Commit or upload reports as CI artifacts.
3. Tune allowlists and severity thresholds.
4. Promote high/critical findings to blocking.

Potential commands:

- `just audit-python`
- `just audit-frontend`
- `just sbom`
- `just license-report`
- `just supply-chain-check`

### 5.7 Configuration and Doctor Hardening

Extend `scripts/doctor.ps1` from basic environment diagnostics to production readiness diagnostics:

- Tool versions.
- Backend venv status.
- Frontend `node_modules` status.
- `scada` CLI availability.
- Local ports.
- Docker status.
- Git status.
- Backend `.env` presence.
- Production unsafe default scan when `ENVIRONMENT=production`.
- DB/Grafana default password warnings.
- `RUN_COLLECTOR` split warnings.
- Alembic current/head check.
- OpenAPI/generated client drift hint.
- Service installation status.
- Backup directory existence and latest backup age.

Do not make `doctor` destructive. If automatic repair is desired, add a separate `doctor-fix` command after the checks are stable.

### 5.8 Agent Contract Drift Protection

Protect the agent-native surface with snapshot-style checks:

- CLI command list snapshot.
- CLI JSON envelope/output shape smoke tests.
- MCP resource/tool list snapshot.
- `agent-harness/skills/SKILL.md` command coverage check.
- Root `AGENTS.md` quick-start examples verified against actual CLI help where practical.

Recommended command:

- `just agent-contract-check`

This should become part of `just check` only after the snapshots are stable and low-noise.

## 6. Detailed Component Design

### 6.1 Scripts

New scripts should live under `scripts/` unless component-specific placement is clearer:

- `scripts/build_release.ps1`
- `scripts/check_versions.ps1`
- `scripts/install-services.ps1`
- `scripts/uninstall-services.ps1`
- `scripts/service-status.ps1`
- `scripts/backup.sh` extension or `scripts/backup.ps1` companion.
- `scripts/restore-smoke.ps1`
- `scripts/sbom.ps1`
- `scripts/agent-contract-check.ps1`

For Windows-first scripts, PowerShell is preferred. Bash can remain for Linux-compatible backup workflows.

### 6.2 `justfile` Additions

Add recipes without disrupting current commands:

```just
release-check
release-build
install-services
uninstall-services
start-services
stop-services
restart-services
service-status
backup-db
restore-smoke
smoke-prodlike
smoke-prodlike-fast
audit-python
audit-frontend
sbom
supply-chain-check
agent-contract-check
```

Promote recipes into `check` only after they are deterministic, reasonably fast, and not environment-specific.

### 6.3 CI Additions

Add CI jobs in this order:

1. Release validation on tags.
2. Artifact build on tags.
3. SBOM/report artifact upload.
4. Non-blocking supply-chain audit on pull requests.
5. Blocking high/critical audit after allowlist tuning.
6. Optional production-like smoke on scheduled runs or manual dispatch.

Production-like smoke may be too heavy for every PR. Prefer:

- Manual `workflow_dispatch`.
- Nightly scheduled run.
- Tag/release candidate run.

### 6.4 Documentation Additions

Add or update:

- `docs/release-build.md`
- `docs/windows-services.md`
- `docs/restore-smoke.md`
- `docs/observability-alerting.md`
- `docs/supply-chain-security.md`
- `docs/agent-contracts.md`

Update existing docs only when they are the canonical entrypoint:

- `README.md` quick command list.
- `DOCKER.md` to mention alerting files if Prometheus config changes.
- `docs/deployment.md` to point to Windows service scripts.
- `docs/backup-recovery.md` to include restore smoke command.

## 7. Acceptance Criteria

### Release

- A version tag builds and attaches release artifacts.
- Checksums are generated and attached.
- Release validation fails when changelog or version metadata is inconsistent.
- Frontend `dist/` is generated from frozen pnpm lockfile.
- CLI/core wheels are buildable and installable in a clean environment.

### Services

- API, collector, and frontend services can be installed, started, stopped, restarted, queried, and uninstalled from documented commands.
- API service uses `RUN_COLLECTOR=False`.
- Collector service uses `RUN_COLLECTOR=True`.
- Service status command reports process state and key log locations.

### Backup/Restore

- A backup command can create a timestamped database backup.
- A restore smoke command can restore a backup into an isolated target.
- Restore smoke verifies Alembic state and critical tables.
- Restore smoke refuses to target the production DB without explicit override.

### Observability

- Prometheus alert rules are committed.
- Alert rules cover API readiness, collector freshness, PLC stale/offline, DB readiness, report failures, and login failure spikes where metrics exist.
- Alert annotations include runbook guidance.
- Grafana dashboards expose the same signals used by alerts.

### Smoke

- `just smoke-prodlike-fast` validates migrations, readiness, CLI JSON, MCP import/resource smoke, and OpenAPI freshness.
- Full `just smoke-prodlike` also validates frontend build and a minimal browser or HTTP smoke.
- The smoke flow works without a real PLC by relying on simulation-safe behavior.

### Supply Chain

- Python and frontend audit commands exist.
- SBOM generation command exists.
- CI can upload audit/SBOM artifacts.
- Blocking thresholds are documented before enabling blocking gates.

### Doctor

- `just doctor` reports service state, config safety warnings, backup age, and Alembic status in addition to current toolchain checks.
- `doctor` remains non-destructive.

### Agent Contracts

- CLI and MCP command/resource drift can be detected by a local command.
- `SKILL.md` command examples stay aligned with real CLI help or command registry.

## 8. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Release scripts become platform-specific | Keep Windows PowerShell first, but avoid hardcoded absolute paths and document Linux equivalents where needed. |
| Supply-chain audits are noisy | Start as report-only CI artifacts; tune allowlists before blocking. |
| Restore smoke accidentally targets production | Require explicit restore target and refuse configured production DB by default. |
| Service scripts hide collector/API split errors | Validate `RUN_COLLECTOR` per service and fail on unsafe combinations. |
| Production-like smoke is slow | Provide `fast` and full variants; run full smoke manually, nightly, or on release candidates. |
| Alert rules create noise | Start conservative, use warning severity, and include runbooks. |
| Agent snapshots are brittle | Snapshot stable command/resource names first; avoid snapshotting volatile values. |

## 9. Rollout Order

1. Release artifact validation and build.
2. Windows service lifecycle.
3. Backup restore smoke.
4. Observability alert rules and runbooks.
5. Production-like smoke test.
6. Supply-chain/SBOM report-only gates.
7. Doctor hardening.
8. Agent contract drift checks.
9. Promote selected stable checks into `just check` and CI blocking jobs.

This order prioritizes field installability and data safety before broader audit and drift tooling.
