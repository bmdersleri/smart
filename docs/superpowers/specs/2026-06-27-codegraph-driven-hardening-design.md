# CodeGraph-Driven Architecture Hardening — Design Spec

**Date:** 2026-06-27
**Status:** Proposed
**Scope:** Architecture and quality hardening based on CodeGraph analysis of the EKONT SMART REPORT codebase. This spec targets runtime correctness, security boundaries, maintainability, and test coverage. It does not change the supported process-based deployment model.

## 1. Goal

Use CodeGraph as the primary discovery tool to reduce risk in the most connected and highest-blast-radius parts of the system.

The target outcome is a safer and easier-to-maintain SCADA reporting platform:

- Scheduler jobs run exactly once in production topology.
- Auth changes have explicit regression coverage.
- Query and upload surfaces have production-grade limits.
- Report generation is decomposed into testable units.
- Large frontend pages are split into smaller components and hooks.
- Agent CLI/MCP contracts remain stable.
- Future architecture reviews can be repeated with CodeGraph commands.

## 2. CodeGraph Findings

The local CodeGraph index was current at analysis time:

| Metric | Value |
|---|---:|
| CodeGraph version | 1.0.1 |
| Files | 364 |
| Nodes | 5,911 |
| Edges | 12,509 |
| Status | Up to date |

Useful commands:

```powershell
codegraph status
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
codegraph explore "report generation scheduled report archive generate_report_from_template" --max-files 8
codegraph explore "authentication token localStorage get_current_user require_role permissions" --max-files 8
codegraph impact get_scheduler --depth 3 --json
codegraph impact generate_report_from_template --depth 3 --json
codegraph impact authenticate_token --depth 3 --json
```

Key findings:

- `get_scheduler` affects readiness, health, scheduled report create/update/toggle paths, and backend lifespan.
- `ScheduledReport` and scheduler behavior have weak direct test signal in CodeGraph output.
- `generate_report_from_template` is a high-complexity orchestration function covering DB reads, stats, anomaly detection, charts, Grafana rendering, file writing, and archive state.
- `authenticate_token` has broad blast radius across dashboard, tags, license, watchlist, Grafana, advanced reports, lab, and realtime endpoints.
- Backend import direction is mostly clean; no mutual backend import pairs were found.
- `scada-core` is consumed by agent CLI and MCP; backend does not depend on it, which is a good boundary.
- Large frontend pages dominate maintainability risk: `Trend`, `AdvancedReports`, `Tags`, `Reports`, `Grafana`, and `ExcelTemplates`.
- Generated OpenAPI TypeScript files dominate the graph and should be excluded from most maintainability metrics.

## 3. Current Architecture Summary

### Backend

- FastAPI application in `scada-reporter/backend/app/main.py`.
- SQLAlchemy async database layer in `app/core/database.py`.
- Alembic migration authority for production.
- Collector split available through `RUN_COLLECTOR`.
- APScheduler starts from API lifespan today.
- Auth and RBAC live in `app/api/auth.py` and `app/core/permissions.py`.
- Reports live across `app/api/reports.py`, `app/api/advanced_reports.py`, and `app/services/report_generator.py`.

### Frontend

- React 19 + Vite + TypeScript.
- Generated OpenAPI types exist under `src/api/generated`.
- Manual API wrapper remains in `src/api/client.ts`.
- JWT access token is stored in `localStorage`.
- Several page components hold large amounts of state, fetching, transformation, and rendering logic in one file.

### Agent Surfaces

- `scada-core` is the shared client/catalog layer.
- Agent CLI consumes `scada-core`.
- MCP server consumes `scada-core`.
- Agent surfaces are intentionally first-class and should be protected as contracts.

## 4. Non-Goals

- Do not rewrite the backend in another language.
- Do not move the supported production runtime into Docker.
- Do not remove the agent-native CLI/MCP approach.
- Do not replace the current frontend stack.
- Do not introduce a new job queue unless the scheduler single-run problem cannot be solved cleanly with the current architecture.
- Do not refactor generated OpenAPI client files manually.
- Do not combine unrelated UI redesign work with the hardening tasks.

## 5. Design Principles

| Principle | Implication |
|---|---|
| Fix high-blast-radius first | Scheduler, auth, report generation, and input boundaries come before cosmetic cleanup. |
| Keep process roles explicit | API, collector, and scheduler responsibilities must be clear and testable. |
| Prefer guardrails over convention | Unsafe production combinations should fail fast or emit unmistakable readiness failures. |
| Split orchestration from pure logic | Report and frontend code should isolate computation from IO and rendering. |
| Preserve agent contracts | CLI/MCP changes require drift checks and documentation updates. |
| Use CodeGraph continuously | Every hardening task should start with `codegraph impact` or `codegraph explore` for the touched symbols. |

## 6. Proposed Architecture Changes

### 6.1 Scheduler Role Separation

Introduce an explicit scheduler runtime role separate from normal API workers.

Recommended settings:

```env
RUN_COLLECTOR=False
RUN_SCHEDULER=False
```

for API workers, and:

```env
RUN_COLLECTOR=False
RUN_SCHEDULER=True
```

for the scheduler process.

Collector remains:

```env
RUN_COLLECTOR=True
RUN_SCHEDULER=False
```

The scheduler process may reuse the FastAPI app lifespan only if the role logic is explicit and safe. A dedicated entrypoint is preferred:

```text
python -m app.scheduler.runner
```

Readiness should distinguish:

- API readiness.
- Scheduler readiness.
- Collector readiness.

`/ready` for API workers should not fail only because `RUN_SCHEDULER=False`. It should report scheduler status as role-aware metadata instead of making every API worker require a local scheduler instance.

#### Acceptance Criteria

- API workers do not start APScheduler when `RUN_SCHEDULER=False`.
- Scheduler process starts APScheduler exactly once per deployment.
- Scheduled jobs do not duplicate under multi-worker API.
- `/ready` remains meaningful for API-only workers.
- Scheduled report create/update/toggle endpoints handle disabled local scheduler mode predictably.

### 6.2 Scheduler Persistence and Concurrency Safety

APScheduler uses SQLAlchemy job store today. This should not be treated as a distributed execution lock by itself.

Add one of the following:

- Single scheduler process enforcement through deployment scripts and readiness checks.
- Database advisory lock around scheduler startup.
- Job-level DB lock around `_run_scheduled_report`.

The conservative first step is single scheduler role enforcement plus tests. Advisory locks can be added if production topology needs active/passive scheduler failover.

#### Acceptance Criteria

- Two scheduler instances cannot silently execute the same scheduled report without detection.
- `_run_scheduled_report` records clear status transitions.
- Failed jobs store actionable error messages.

### 6.3 Report Generation Decomposition

Refactor `generate_report_from_template` into smaller units:

```text
resolve_time_range(template)
load_report_tags(db, tag_ids)
load_tag_readings(db, tag_id, start, end)
build_per_tag_report_data(...)
render_grafana_panels(...)
build_report_output(...)
write_report_file(...)
persist_archive_success(...)
persist_archive_failure(...)
```

Pure functions should receive explicit inputs and return structured outputs. IO functions should be isolated and easier to mock.

#### Acceptance Criteria

- Existing report behavior remains unchanged.
- Unit tests cover stats/anomaly/chart payload construction without real file IO.
- Grafana render failure remains tolerated when intended.
- Archive state transitions are covered for success and failure.

### 6.4 Query Endpoint Hardening

The read-only SQL endpoint is useful for agents, but regex filtering is not enough for production safety.

Add layered controls:

- Dedicated read-only database role for the query endpoint.
- `statement_timeout`.
- Maximum returned rows enforced at SQL level.
- Maximum query text length.
- Rejection of multiple statements.
- Optional SQL parser validation for allowed statement types.
- Audit log entry for query usage by user.

#### Acceptance Criteria

- Mutating SQL cannot execute even if regex checks miss it.
- Long-running SQL is cancelled.
- Large result sets do not load fully into application memory.
- Operators can identify who ran a query.

### 6.5 Upload Boundary Hardening

Harden upload endpoints:

- Tag Excel import.
- Tag CSV import.
- Excel template inspection.
- Excel template creation through base64.
- License upload.

Controls:

- Maximum file size by endpoint.
- MIME and magic-byte checks where practical.
- XLSX zip-bomb protection.
- Maximum row/sheet/cell count.
- CSV maximum row count.
- Clear validation errors.
- Tests for oversized and malformed uploads.

#### Acceptance Criteria

- Oversized uploads fail before full parsing.
- Invalid file types fail consistently.
- Malformed Excel/CSV/license payloads return controlled 4xx errors.
- Upload parsing cannot exhaust memory under expected limits.

### 6.6 Auth and Session Hardening

Auth has broad blast radius. Improve safety and coverage in stages:

Short term:

- Add explicit tests for `authenticate_token`.
- Add tests for SSE-scoped token rejection on normal API endpoints.
- Add tests for inactive users and token version mismatch.
- Reduce default production access-token duration or document production override.
- Add security headers and CSP where frontend is served.

Medium term:

- Evaluate HttpOnly Secure SameSite cookie auth.
- If bearer tokens remain, add refresh-token rotation or shorter access token lifetime.
- Add frontend XSS guardrails and dependency audit gates.

#### Acceptance Criteria

- Auth regression tests cover normal token, SSE token, invalid scope, inactive user, version mismatch, and expired token.
- Frontend token storage risk is documented.
- Production deployment docs include recommended token TTL and HTTPS requirements.

### 6.7 Frontend Decomposition

Split the largest page components without changing UI behavior.

Targets:

- `Trend.tsx`
- `AdvancedReports.tsx`
- `Tags.tsx`
- `Reports.tsx`
- `Grafana.tsx`
- `ExcelTemplates.tsx`

Recommended pattern:

- Extract data fetching into hooks.
- Extract local persistence into small utility modules.
- Extract modal forms into separate components.
- Extract tables and toolbar controls.
- Keep generated API types as source of truth where possible.

#### Acceptance Criteria

- No single hand-written React component should remain above 250 lines unless justified.
- Existing tests pass.
- New component tests cover extracted logic where risk is non-trivial.
- The UI layout and behavior remain unchanged unless explicitly approved.

### 6.8 API Client Consolidation

The project has both generated API types and a manual `src/api/client.ts` wrapper. Keep both only where intentional.

Recommended approach:

- Use generated types for request/response shapes.
- Keep a small manual axios instance only for auth headers, binary downloads, and special cases.
- Avoid duplicating endpoint type definitions manually.
- Add a lint or test check for common drift-prone manual types.

#### Acceptance Criteria

- Manual type definitions in `client.ts` are reduced or explicitly justified.
- Contract freshness check remains green.
- Binary endpoints and SSE token flow continue to work.

### 6.9 Agent Contract Protection

Protect agent-native interfaces:

- CLI command group list.
- JSON output shape for representative commands.
- MCP resource/tool names.
- `SKILL.md` command coverage.

Add a local command:

```text
just agent-contract-check
```

#### Acceptance Criteria

- CLI/MCP contract drift is detected before release.
- Snapshots avoid volatile values.
- `AGENTS.md` examples remain aligned with actual CLI behavior.

### 6.10 CodeGraph Review Workflow

Add a repeatable architecture review command or documented workflow.

For every non-trivial change:

```powershell
codegraph sync
codegraph impact <symbol> --depth 3 --json
codegraph explore "<feature or flow>" --max-files 8
```

For release hardening reviews:

```powershell
codegraph status
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
codegraph explore "authentication token get_current_user require_role permissions" --max-files 8
codegraph explore "report generation scheduled report archive" --max-files 8
```

#### Acceptance Criteria

- CodeGraph commands are documented in contributor or architecture docs.
- The project has a checklist for using CodeGraph before high-blast-radius edits.

## 7. Testing Strategy

### Backend

Add focused tests for:

- Scheduler role settings.
- Scheduler startup disabled in API role.
- Scheduler startup enabled in scheduler role.
- Scheduled report create/update/toggle behavior when local scheduler is disabled.
- `_run_scheduled_report` success and failure.
- Query endpoint timeouts and row limits.
- Upload size and malformed file handling.
- Auth token scope/version/inactive-user behavior.
- Report generator helper functions after decomposition.

### Frontend

Add or preserve tests for:

- Extracted hooks.
- Modal form validation.
- Token logout behavior on 401.
- Trend selection and chart control logic.
- Advanced report archive/schedule flows.

### Agent/MCP

Add tests for:

- CLI command availability.
- Representative JSON outputs.
- MCP resource/tool registration.
- `SKILL.md` coverage.

## 8. Observability

Add or verify metrics for:

- Scheduler process running.
- Scheduler job started/completed/failed.
- Report generation duration.
- Upload rejection counts by reason.
- Query endpoint duration, row count, and timeout count.
- Auth failures and rate-limit events.

Metrics should avoid high-cardinality labels. Usernames and SQL text must not be metric labels.

## 9. Migration and Compatibility

The scheduler role change is the only runtime topology change.

Compatibility requirements:

- Development defaults may keep scheduler enabled if that preserves convenience, but production docs must be explicit.
- Existing scheduled report rows remain valid.
- Existing APScheduler job IDs remain stable where possible.
- Existing report archive files remain readable.
- CLI/MCP command behavior remains backward-compatible.

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Scheduler role split breaks local dev convenience | Keep dev recipe that starts API with scheduler enabled, but make production recipes explicit. |
| Readiness semantics become confusing | Return role-aware readiness details and document API/scheduler/collector expectations. |
| Report refactor changes generated files | Add snapshot or structural tests around archive status, file type, and summary JSON. |
| Upload limits reject legitimate plant data | Start with configurable limits and document how to raise them. |
| SQL endpoint becomes less useful for agents | Keep read-only discovery capability, but move enforcement to DB role and timeouts. |
| Frontend refactor causes UI regressions | Use Playwright/Vitest checks and keep changes behavior-preserving. |
| Agent contract snapshots become noisy | Snapshot stable command/resource names, not timestamps or live data. |

## 11. Rollout Order

1. Scheduler role separation and tests.
2. Scheduler concurrency/status hardening.
3. Auth regression tests.
4. Query endpoint hardening.
5. Upload boundary hardening.
6. Report generation decomposition.
7. Frontend decomposition.
8. API client consolidation.
9. Agent contract checks.
10. CodeGraph review workflow documentation.

This order prioritizes correctness and security boundaries before maintainability refactors.

## 12. Final Acceptance Criteria

- Multi-worker API deployment cannot duplicate scheduled jobs.
- Scheduler role is explicit in config, readiness, docs, and tests.
- Auth token validation has direct regression coverage.
- Query endpoint is enforced by DB-level read-only controls and timeouts.
- Upload endpoints enforce size/type/content limits.
- Report generation is decomposed and covered by focused tests.
- Large frontend pages are reduced into smaller components/hooks.
- Agent CLI/MCP contracts have a drift check.
- CodeGraph commands are documented and usable for future architecture reviews.
