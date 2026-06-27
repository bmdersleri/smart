# Production Infrastructure Maturity Implementation Plan

> **For agentic workers:** implement task-by-task. Keep each task small, verify with targeted commands, and avoid changing runtime behavior outside the task scope. This plan is based on `docs/superpowers/specs/2026-06-23-production-infrastructure-maturity-design.md`.

**Goal:** Add infrastructure that makes EKONT SMART REPORT easier to release, install, operate, restore, observe, and verify in production-like conditions while preserving the documented process-based deployment model.

**Architecture:** Keep the API, collector, and frontend as native processes. Docker remains local infrastructure only. Add release artifacts, Windows service lifecycle scripts, restore smoke tests, alerting rules, production-like smoke commands, supply-chain reports, doctor hardening, and agent contract drift checks as layered infrastructure around the existing application.

**Tech Stack:** Python 3.14, FastAPI, Alembic, pytest, PowerShell, Bash where already used, pnpm, Vite, GitHub Actions, Prometheus, Grafana, optional Alertmanager, Click CLI, MCP server tests.

## Global Constraints

- Do not add production Dockerfiles or production Compose app services unless a separate architecture decision reverses the existing process-based deployment policy.
- Do not make `doctor` or smoke commands destructive.
- Do not run restore smoke against the configured production database unless an explicit isolated restore target is provided.
- Keep `RUN_COLLECTOR=False` for API processes and `RUN_COLLECTOR=True` for the collector process.
- Prefer `just` recipes as the local entrypoint for every new infrastructure workflow.
- Add CI blocking only after the corresponding local command is deterministic.
- Keep scripts path-portable; avoid hardcoded developer-specific absolute paths.
- Update docs with every operator-facing command.
- Do not promote slow or environment-dependent checks into `just check` until they are stable.

---

## Task 1: Release Artifact Validation

**Purpose:** Make release tags fail early when version metadata, changelog entries, or generated contracts are inconsistent.

**Files:**

- Create: `scripts/check_release.ps1`
- Modify: `justfile`
- Modify: `.github/workflows/release.yml`
- Update: `docs/release-build.md` or create it if missing

**Steps:**

- [ ] Define the release metadata rules:
  - Git tag must be `vX.Y.Z`.
  - `CHANGELOG.md` must contain a matching `## [X.Y.Z]` section.
  - Frontend package version must either match `X.Y.Z` or be documented as intentionally independent.
  - CLI/core/backend versions must either match `X.Y.Z` or be documented as intentionally independent.
  - OpenAPI/generated client must be fresh.

- [ ] Implement `scripts/check_release.ps1`:
  - Accept `-Version` or infer from `GITHUB_REF_NAME`.
  - Parse and validate `CHANGELOG.md`.
  - Read known version files.
  - Run or instruct `just contract-check` as part of validation.
  - Print concise errors and exit non-zero on mismatch.

- [ ] Add `just release-check`:
  - Calls `scripts/check_release.ps1`.
  - Documents optional `version` parameter if needed.

- [ ] Wire `release-check` into `.github/workflows/release.yml` before creating the GitHub Release.

- [ ] Document:
  - How to prepare a release.
  - What metadata must be updated.
  - How to run `just release-check` locally.

**Verification:**

- [ ] Run `just release-check` for the current or sample version.
- [ ] Confirm it fails clearly for a deliberately missing changelog version in a local temporary test or manual reasoning.
- [ ] Confirm release workflow YAML remains valid.

**Definition of Done:**

- Tag release validation exists locally and in CI.
- Release validation checks changelog and version consistency.
- Failures are clear enough for an operator or maintainer to fix without reading script internals.

---

## Task 2: Release Artifact Build

**Purpose:** Attach installable artifacts to GitHub releases instead of publishing release notes only.

**Files:**

- Create: `scripts/build_release.ps1`
- Modify: `justfile`
- Modify: `.github/workflows/release.yml`
- Update: `docs/release-build.md`

**Steps:**

- [ ] Implement frontend artifact build:
  - `cd scada-reporter/frontend`
  - `pnpm install --frozen-lockfile`
  - `pnpm build`
  - Zip `dist/` as `ekont-smart-report-frontend-dist-vX.Y.Z.zip`.

- [ ] Implement Python package builds:
  - Build `scada-core` wheel/sdist.
  - Build `scada-reporter-cli` wheel/sdist.
  - Ensure a clean environment can install both artifacts.

- [ ] Implement backend source/runtime artifact:
  - Include backend source files needed for process-based deployment.
  - Include `requirements.lock`.
  - Exclude local `.env`, `.venv`, databases, caches, reports, and generated local artifacts.

- [ ] Export OpenAPI snapshot:
  - Include `scada-reporter/frontend/openapi.json` as `openapi-vX.Y.Z.json`.

- [ ] Generate checksums:
  - Produce `checksums-vX.Y.Z.sha256`.
  - Include every artifact.

- [ ] Add `just release-build`:
  - Depends on or calls `release-check`.
  - Writes artifacts to `artifacts/release/vX.Y.Z/`.

- [ ] Update GitHub release workflow:
  - Run `release-build`.
  - Attach generated artifacts to the GitHub Release.

**Verification:**

- [ ] Run `just release-build version="X.Y.Z"` locally or with a dry-run mode.
- [ ] Confirm artifact names are deterministic.
- [ ] Confirm checksums validate.
- [ ] Confirm generated zips do not contain secrets or virtualenvs.

**Definition of Done:**

- A release tag creates installable frontend and Python artifacts.
- Checksums are published.
- Backend source artifact is safe to distribute.

---

## Task 3: Windows Service Lifecycle Scripts

**Purpose:** Make process-based production deployment repeatable on Windows.

**Files:**

- Create: `scripts/install-services.ps1`
- Create: `scripts/uninstall-services.ps1`
- Create: `scripts/service-status.ps1`
- Modify: `justfile`
- Create or update: `docs/windows-services.md`
- Optionally update: `docs/deployment.md`

**Steps:**

- [ ] Choose the Windows service mechanism:
  - Prefer a documented wrapper already accepted by the project, or use built-in `sc.exe`/PowerShell service APIs if sufficient.
  - Document prerequisite installation if an external wrapper is required.

- [ ] Define service names:
  - `EkontSmartReportApi`
  - `EkontSmartReportCollector`
  - `EkontSmartReportFrontend`

- [ ] Implement API service install:
  - Working directory: `scada-reporter/backend`.
  - Command: production API command from `docs/deployment.md`.
  - Environment: `RUN_COLLECTOR=False`.
  - Logs: predictable path under a configured logs directory.

- [ ] Implement collector service install:
  - Working directory: `scada-reporter/backend`.
  - Command: `python -m app.collector.runner`.
  - Environment: `RUN_COLLECTOR=True`.
  - Enforce single-instance expectation in docs and status output.

- [ ] Implement frontend service install:
  - Serve built `frontend/dist/` with the chosen static server.
  - Fail clearly if `dist/` does not exist.

- [ ] Implement service status:
  - Report installed/not installed.
  - Report running/stopped.
  - Report command path.
  - Report environment file path.
  - Report log path.
  - Warn on unsafe `RUN_COLLECTOR` split.

- [ ] Add `just` recipes:
  - `install-services`
  - `uninstall-services`
  - `start-services`
  - `stop-services`
  - `restart-services`
  - `service-status`

- [ ] Document:
  - Prerequisites.
  - Install sequence.
  - Upgrade sequence.
  - Rollback sequence.
  - Log locations.
  - Common failure modes.

**Verification:**

- [ ] Run script syntax checks.
- [ ] Run `just service-status` on a machine without services and confirm clear output.
- [ ] If safe in the environment, install/uninstall a test service name or dry-run mode.

**Definition of Done:**

- Service commands exist and are documented.
- API/collector environment split is enforced or clearly warned.
- Status output is useful for support.

---

## Task 4: Backup Command and Restore Smoke

**Purpose:** Prove that backups can be restored, not merely created.

**Files:**

- Modify: `scripts/backup.sh` or create `scripts/backup.ps1`
- Create: `scripts/restore-smoke.ps1`
- Modify: `justfile`
- Update: `docs/backup-recovery.md`
- Create: `docs/restore-smoke.md` if the runbook becomes too large

**Steps:**

- [ ] Add `just backup-db`:
  - Create timestamped PostgreSQL custom-format dump.
  - Accept output directory.
  - Print resulting backup path.
  - Avoid embedding passwords in command history where practical.

- [ ] Implement restore target safeguards:
  - Require explicit restore database or isolated local target.
  - Refuse to restore into the configured application database by default.
  - Print the target before running restore.

- [ ] Implement `scripts/restore-smoke.ps1`:
  - Accept `-BackupPath`.
  - Accept `-TargetDatabaseUrl` or target components.
  - Create or clear only the isolated target after confirmation/dry-run rules.
  - Run `pg_restore` or `psql` based on file format.
  - Run Alembic `current`.
  - Run Alembic `upgrade head`.
  - Query critical tables:
    - users
    - tags
    - tag_readings
    - plc_configs where present
    - report history/archive tables where present
  - Optionally start API against the restore target and call `/ready`.

- [ ] Add `just restore-smoke`:
  - Defaults to latest backup in configured backup directory.
  - Allows explicit backup path.

- [ ] Document:
  - Required tools.
  - Safe restore target setup.
  - Expected success output.
  - Failure interpretation.

**Verification:**

- [ ] Run script syntax checks.
- [ ] Run restore smoke against a small local/dev backup if available.
- [ ] Confirm script refuses unsafe target.
- [ ] Confirm docs clearly state non-destructive expectations.

**Definition of Done:**

- Backup creation has a first-class command.
- Restore smoke can verify a backup in isolation.
- The runbook includes the automated verification path.

---

## Task 5: Prometheus Alert Rules and Runbooks

**Purpose:** Convert existing observability data into actionable alerts.

**Files:**

- Create: `scada-reporter/docker/prometheus/alerts.yml`
- Modify: `scada-reporter/docker/prometheus/prometheus.yml`
- Create: `docs/observability-alerting.md`
- Optionally modify: Grafana dashboard JSON files
- Optionally create: `scada-reporter/docker/alertmanager/alertmanager.yml`

**Steps:**

- [ ] Inventory current metrics:
  - API HTTP/request metrics.
  - Collector tick/read/write metrics.
  - PLC health metrics.
  - Report generation metrics.
  - Login/rate-limit metrics.
  - DB/readiness metrics.

- [ ] Add initial Prometheus alert groups:
  - API readiness down.
  - API high 5xx rate if metric exists.
  - API high latency if histogram exists.
  - Collector stale/no tick.
  - PLC offline/stale readings if metric exists.
  - Report generation failures if metric exists.
  - Login failures spike if metric exists.
  - Prometheus scrape target down.

- [ ] Add labels and annotations:
  - `severity`
  - `component`
  - `summary`
  - `description`
  - `runbook_url`

- [ ] Update Prometheus config to load `alerts.yml`.

- [ ] Add `just prometheus-check` if feasible:
  - Validate config and alert files using `promtool` when available.

- [ ] Write runbook docs:
  - Meaning of each alert.
  - First checks.
  - Common causes.
  - Recovery steps.
  - Escalation notes.

- [ ] Align Grafana dashboards:
  - Add panels for signals used by alerts if missing.
  - Keep dashboard provisioning version-controlled.

**Verification:**

- [ ] Run `promtool check config` when available.
- [ ] Start Prometheus local infra and confirm it loads alert rules.
- [ ] Confirm alert rule names and labels are stable.

**Definition of Done:**

- Alert rules are version-controlled.
- Runbooks exist for each alert.
- Prometheus config loads alert rules successfully.

---

## Task 6: Optional Alertmanager Routing

**Purpose:** Provide an operator-ready path for routing alerts without forcing it on every local developer.

**Files:**

- Create: `scada-reporter/docker/alertmanager/alertmanager.yml`
- Modify: `scada-reporter/docker/docker-compose.yml`
- Update: `DOCKER.md`
- Update: `docs/observability-alerting.md`

**Steps:**

- [ ] Add Alertmanager as an optional Compose profile:
  - Profile name: `alertmanager`.
  - Port: `9093`.
  - Config mounted read-only.

- [ ] Configure default local route:
  - Safe no-op or local-only receiver.
  - No real secrets committed.

- [ ] Document production routing:
  - Email.
  - Webhook.
  - Slack/Teams-compatible webhook pattern.
  - Secret handling.

- [ ] Update Prometheus config with optional Alertmanager target guidance.

**Verification:**

- [ ] Run Compose profile locally if Docker is available.
- [ ] Confirm Alertmanager starts with placeholder config.
- [ ] Confirm docs state that real routing secrets are not committed.

**Definition of Done:**

- Alertmanager can be enabled intentionally.
- Default config is safe for local development.
- Production routing is documented.

---

## Task 7: Production-Like Smoke Test

**Purpose:** Validate real deployment topology before releases and major merges.

**Files:**

- Create: `scripts/smoke-prodlike.ps1`
- Modify: `justfile`
- Optionally create: `docs/prodlike-smoke.md`
- Update: `README.md` command list if appropriate

**Steps:**

- [ ] Define smoke modes:
  - `fast`: migrations, readiness, CLI JSON, MCP import/resource smoke, OpenAPI freshness.
  - `full`: fast checks plus frontend build and minimal frontend smoke.

- [ ] Implement infrastructure preflight:
  - Check PostgreSQL/TimescaleDB port or Docker service health.
  - Check Redis if required by readiness/scheduler.
  - Print missing prerequisites.

- [ ] Implement DB phase:
  - Run Alembic upgrade.
  - Seed required users if missing.
  - Verify Alembic head.

- [ ] Implement API phase:
  - Start API with `RUN_COLLECTOR=False` on a free or configured port.
  - Wait for `/live`.
  - Wait for `/ready`.
  - Capture logs to artifacts directory.

- [ ] Implement collector phase:
  - Start collector with `RUN_COLLECTOR=True`.
  - Use simulation-safe mode if available.
  - Verify collector does not block API readiness.
  - Capture logs.

- [ ] Implement CLI phase:
  - Run `scada health --json-output`.
  - Run a read-only discovery command with JSON output.
  - Validate JSON parse.

- [ ] Implement MCP phase:
  - Import MCP server.
  - Run existing MCP tests or a lightweight resource smoke.

- [ ] Implement frontend phase for full mode:
  - `pnpm install --frozen-lockfile`.
  - `pnpm build`.
  - Optionally serve `dist/` and perform HTTP or Playwright smoke.

- [ ] Ensure cleanup:
  - Stop started API/collector processes.
  - Print log paths.
  - Do not kill unrelated Python processes.

- [ ] Add `just smoke-prodlike-fast`.
- [ ] Add `just smoke-prodlike`.

**Verification:**

- [ ] Run fast smoke locally.
- [ ] Confirm cleanup happens on failure.
- [ ] Confirm output identifies the failing phase.

**Definition of Done:**

- A maintainer can validate production topology with one command.
- The smoke test does not require a physical PLC.
- Logs are retained for debugging.

---

## Task 8: Supply-Chain Reports

**Purpose:** Add dependency risk visibility before enforcing blocking policy.

**Files:**

- Create: `scripts/supply-chain.ps1`
- Modify: `justfile`
- Modify: `.github/workflows/ci.yml` or create a separate workflow
- Create: `docs/supply-chain-security.md`
- Optionally update: `scripts/generate_license.py` or license report docs if related

**Steps:**

- [ ] Add Python audit command:
  - Use the tool already present or chosen by the team.
  - Prefer pinned lock input.
  - Output machine-readable and human-readable reports.

- [ ] Add frontend audit command:
  - Use `pnpm audit` or a chosen scanner.
  - Start report-only.

- [ ] Add SBOM generation:
  - Python SBOM.
  - Frontend SBOM.
  - Output to `artifacts/sbom/`.

- [ ] Add license report:
  - Reuse existing license generation/report script where possible.
  - Document allowed/review-required licenses.

- [ ] Add `just` recipes:
  - `audit-python`
  - `audit-frontend`
  - `sbom`
  - `supply-chain-check`

- [ ] Add CI artifact upload:
  - Upload audit reports.
  - Upload SBOM files.
  - Keep non-blocking initially unless high-confidence.

- [ ] Document promotion policy:
  - Report-only phase.
  - Tuning phase.
  - Blocking high/critical phase.

**Verification:**

- [ ] Run supply-chain report locally.
- [ ] Confirm reports are written to predictable paths.
- [ ] Confirm CI uploads reports.

**Definition of Done:**

- Dependency and SBOM reports can be produced locally and in CI.
- Blocking policy is documented but not prematurely enforced.

---

## Task 9: Doctor Hardening

**Purpose:** Make `just doctor` useful for both development and production readiness triage.

**Files:**

- Modify: `scripts/doctor.ps1`
- Modify: `justfile` if needed
- Update: `README.md` or `docs/deployment.md`

**Steps:**

- [ ] Add environment/config checks:
  - Backend `.env` exists.
  - `ENVIRONMENT=production` unsafe defaults warning.
  - Default DB password warning.
  - Grafana default password warning.
  - Unsafe CORS warning.
  - `AUTO_CREATE_TABLES` warning for production.

- [ ] Add service checks:
  - API service installed/running.
  - Collector service installed/running.
  - Frontend service installed/running.
  - Grafana/Prometheus service or port status.

- [ ] Add database checks:
  - DB port reachable.
  - Alembic current/head check when backend venv exists.
  - Optional `/ready` check if API is running.

- [ ] Add backup checks:
  - Backup directory exists.
  - Latest backup age.
  - Warn if no backup found.

- [ ] Add contract checks:
  - Hint when OpenAPI/generated client drift exists.
  - Do not regenerate files inside doctor.

- [ ] Keep output concise:
  - Sections.
  - `OK`, `WARN`, `FAIL`.
  - Suggested command for common fixes.

**Verification:**

- [ ] Run `just doctor`.
- [ ] Confirm it works when optional services are missing.
- [ ] Confirm it does not modify files.

**Definition of Done:**

- `doctor` reports operational risks beyond tool availability.
- Output remains readable and non-destructive.

---

## Task 10: Agent Contract Drift Checks

**Purpose:** Protect the CLI/MCP/skill surface that coding agents depend on.

**Files:**

- Create: `scripts/agent-contract-check.ps1`
- Add or update tests under:
  - `scada-reporter/agent-harness/tests/`
  - `mcp-servers/mcp-scada/tests/`
- Modify: `justfile`
- Create: `docs/agent-contracts.md`

**Steps:**

- [ ] Define stable contract surfaces:
  - CLI command groups.
  - Read-only JSON command shapes.
  - MCP resource names.
  - MCP tool names.
  - `agent-harness/skills/SKILL.md` documented commands.

- [ ] Add CLI command list snapshot:
  - Avoid volatile help text.
  - Snapshot command names and group structure.

- [ ] Add CLI JSON smoke:
  - Use mocked HTTP client where possible.
  - Validate that `--json-output` emits parseable JSON for representative read commands.

- [ ] Add MCP contract smoke:
  - Snapshot resource/tool names or existing tests extended with stable lists.

- [ ] Add `SKILL.md` coverage check:
  - Parse documented commands.
  - Compare to real CLI command availability where practical.

- [ ] Add `just agent-contract-check`.

- [ ] Decide promotion:
  - Keep standalone initially.
  - Promote into `check` after snapshots are stable.

**Verification:**

- [ ] Run `just agent-contract-check`.
- [ ] Confirm intentional command changes require updating snapshots/docs.

**Definition of Done:**

- Agent-facing drift has an explicit local check.
- The check is stable enough to be useful and not noisy.

---

## Task 11: Documentation Index Updates

**Purpose:** Make new infrastructure discoverable from existing entrypoints.

**Files:**

- Modify: `README.md`
- Modify: `DOCKER.md`
- Modify: `docs/deployment.md`
- Modify: `docs/backup-recovery.md`
- Add/update docs created by earlier tasks

**Steps:**

- [ ] Add release section:
  - `just release-check`
  - `just release-build`

- [ ] Add service section:
  - Windows service lifecycle commands.
  - Link to `docs/windows-services.md`.

- [ ] Add backup verification section:
  - `just backup-db`
  - `just restore-smoke`

- [ ] Add observability section:
  - Prometheus alerts.
  - Optional Alertmanager.
  - Runbook location.

- [ ] Add smoke section:
  - `just smoke-prodlike-fast`
  - `just smoke-prodlike`

- [ ] Add supply-chain section:
  - `just supply-chain-check`
  - SBOM output location.

- [ ] Add agent contract section:
  - `just agent-contract-check`

**Verification:**

- [ ] Check links.
- [ ] Check command names match `justfile`.
- [ ] Keep README concise; put details in docs.

**Definition of Done:**

- Operators and maintainers can find every new infrastructure workflow from the main docs.

---

## Task 12: CI Promotion Strategy

**Purpose:** Promote stable infrastructure checks into CI without making every PR slow or flaky.

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify or create: `.github/workflows/release.yml`
- Optionally create: `.github/workflows/nightly.yml`
- Update: docs created above

**Steps:**

- [ ] Classify checks:
  - Every PR: fast, deterministic checks.
  - Nightly: production-like full smoke, supply-chain reports.
  - Tags: release validation and artifact build.
  - Manual dispatch: restore smoke and full smoke.

- [ ] Add report-only jobs first:
  - Supply-chain reports.
  - SBOM generation.

- [ ] Add scheduled smoke:
  - Full `smoke-prodlike` if runtime is stable enough for GitHub Actions.
  - Otherwise document local/manual release candidate execution.

- [ ] Promote stable checks:
  - `agent-contract-check` after snapshots stabilize.
  - `prometheus-check` after promtool availability is deterministic.
  - High/critical supply-chain blocking after allowlist tuning.

- [ ] Ensure artifacts upload:
  - Smoke logs.
  - Audit reports.
  - SBOM files.
  - Release artifacts on tags.

**Verification:**

- [ ] Run workflow syntax validation by pushing to a test branch or using local action linting if available.
- [ ] Confirm PR checks remain reasonably fast.
- [ ] Confirm slow checks are not required for every PR unless explicitly intended.

**Definition of Done:**

- CI has a clear promotion path.
- Release, nightly, and PR checks serve different purposes.
- Heavy checks do not block routine development until proven stable.

---

## Recommended Execution Order

1. Task 1: Release Artifact Validation
2. Task 2: Release Artifact Build
3. Task 3: Windows Service Lifecycle Scripts
4. Task 4: Backup Command and Restore Smoke
5. Task 5: Prometheus Alert Rules and Runbooks
6. Task 6: Optional Alertmanager Routing
7. Task 7: Production-Like Smoke Test
8. Task 8: Supply-Chain Reports
9. Task 9: Doctor Hardening
10. Task 10: Agent Contract Drift Checks
11. Task 11: Documentation Index Updates
12. Task 12: CI Promotion Strategy

The first four tasks produce the highest field value: shippable releases, repeatable service installation, and verified recovery.

## Final Acceptance Checklist

- [ ] Release tags create validated artifacts with checksums.
- [ ] Windows service lifecycle is scripted and documented for API, collector, and frontend.
- [ ] Backup creation and isolated restore smoke are available through `just`.
- [ ] Prometheus alert rules and runbooks are committed.
- [ ] Optional Alertmanager routing is documented and safe by default.
- [ ] Production-like smoke commands validate topology without a real PLC.
- [ ] Supply-chain audit and SBOM reports are generated locally and in CI.
- [ ] `just doctor` reports config, service, DB, backup, and contract health without changing files.
- [ ] Agent CLI/MCP/skill contract drift has a local check.
- [ ] Documentation entrypoints link to each new workflow.
- [ ] CI promotion is staged so heavy or noisy checks do not block normal PRs prematurely.
