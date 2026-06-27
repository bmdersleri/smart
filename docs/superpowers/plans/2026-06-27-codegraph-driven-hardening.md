# CodeGraph-Driven Architecture Hardening Implementation Plan

> **For agentic workers:** implement task-by-task. Start each task by running the listed CodeGraph command, then make a narrow change and verify with targeted tests. This plan is based on `docs/superpowers/specs/2026-06-27-codegraph-driven-hardening-design.md`.

**Goal:** Reduce the highest-risk areas identified by CodeGraph: scheduler runtime duplication, auth blast radius, query/upload boundaries, report generator complexity, large frontend components, API client drift, and agent contract drift.

**Architecture:** Keep the existing Python/FastAPI backend, React/Vite frontend, process-based production deployment, agent CLI, MCP server, and `scada-core` boundary. Add explicit runtime roles, stronger boundaries, smaller modules, and better tests.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, APScheduler, pytest, React 19, Vite, TypeScript, Vitest, Playwright, Click CLI, FastMCP, CodeGraph CLI.

## Current Implementation Status

Completed in `codegraph-hardening-subagents`:

- Task 1 / Task 3: scheduler role configuration and role-aware readiness.
- Task 2: dedicated scheduler runner.
- Task 4: scheduled job overlap guard and bounded scheduler error text.
- Task 6: direct auth token validation regression tests.
- Task 7: production bearer-token TTL warning and deployment documentation.
- Task 8: query endpoint guardrails for SQL length, single-statement enforcement, row caps, and bounded fetches.
- Task 9: shared upload limit and payload validation utilities.

Still pending:

- Task 5: scheduler API create/update/toggle/delete tests.
- Task 10: apply upload hardening to endpoint implementations.
- Task 11 and later: report generator decomposition, frontend decomposition, API client cleanup, and agent contract drift checks.

## Global Constraints

- Use CodeGraph before editing high-blast-radius symbols.
- Keep API, collector, and scheduler roles explicit.
- Do not change generated OpenAPI files manually.
- Do not change UI behavior during frontend decomposition unless explicitly scoped.
- Do not remove the agent-native CLI/MCP surface.
- Keep production Dockerfiles out of scope.
- Preserve local development convenience where practical.
- Add tests close to the risk being changed.

---

## Task 1: Add Scheduler Role Configuration

**Purpose:** Prevent API workers from always starting APScheduler.

**CodeGraph preflight:**

```powershell
codegraph impact get_scheduler --depth 3 --json
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/core/config.py`
- Modify: `scada-reporter/backend/app/main.py`
- Modify: `scada-reporter/backend/.env.production.example`
- Modify: `docs/deployment.md`
- Modify: `DOCKER.md` if production topology notes mention scheduler
- Add/modify tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Add `RUN_SCHEDULER: bool` to settings.
- [ ] Choose defaults:
  - Development: either `True` for convenience or documented recipe-specific behavior.
  - Production template: `False` for API service.
  - Scheduler service: `True`.
- [ ] In `lifespan`, call `start_scheduler()` only when `RUN_SCHEDULER=True`.
- [ ] Keep collector logic controlled only by `RUN_COLLECTOR`.
- [ ] Add production warnings/errors for unsafe combinations:
  - API docs must show `RUN_COLLECTOR=False`.
  - API docs must show `RUN_SCHEDULER=False`.
  - Scheduler docs must show `RUN_SCHEDULER=True`.
- [ ] Update `/health` response to include `scheduler_enabled` and `scheduler_running`.

**Verification:**

- [ ] Run targeted config tests.
- [ ] Add test proving scheduler does not start when `RUN_SCHEDULER=False`.
- [ ] Add test proving scheduler starts when `RUN_SCHEDULER=True`.
- [ ] Run backend tests related to config/lifespan if available.

**Definition of Done:**

- API process can run without local scheduler.
- Scheduler state is visible in health output.
- Production env template documents the split.

---

## Task 2: Add Dedicated Scheduler Runner

**Purpose:** Provide a clean production entrypoint for exactly one scheduler process.

**CodeGraph preflight:**

```powershell
codegraph node start_scheduler
codegraph impact start_scheduler --depth 3 --json
```

**Files:**

- Create: `scada-reporter/backend/app/scheduler/__init__.py`
- Create: `scada-reporter/backend/app/scheduler/runner.py`
- Modify: `justfile`
- Modify: `docs/deployment.md`
- Add tests if runner logic can be isolated

**Steps:**

- [ ] Create a scheduler runner module.
- [ ] Initialize configuration and production config validation.
- [ ] Initialize database schema only if appropriate for the role.
- [ ] Start APScheduler.
- [ ] Keep the process alive until interrupted.
- [ ] Handle SIGINT/SIGTERM cleanly where practical.
- [ ] Add `just run-scheduler`.
- [ ] Document production scheduler command:

```powershell
cd scada-reporter/backend
RUN_COLLECTOR=False RUN_SCHEDULER=True python -m app.scheduler.runner
```

**Verification:**

- [ ] Import smoke: `python -m app.scheduler.runner` should import without side effects that start jobs during import.
- [ ] Unit test runner helper functions if extracted.
- [ ] Confirm `just run-scheduler` command is documented.

**Definition of Done:**

- Production has a first-class scheduler command.
- API no longer needs to own scheduled jobs.

---

## Task 3: Make Readiness Role-Aware

**Purpose:** Avoid false `/ready` failures in API-only workers while still exposing scheduler state.

**CodeGraph preflight:**

```powershell
codegraph node readiness
codegraph impact readiness --depth 3 --json
```

**Files:**

- Modify: `scada-reporter/backend/app/api/health.py`
- Modify: `scada-reporter/backend/app/main.py` if `/health` shape changes
- Add/modify tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Keep DB and Alembic checks mandatory for API readiness.
- [ ] Make scheduler readiness conditional on `RUN_SCHEDULER=True`.
- [ ] Return structured role data:

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

- [ ] Ensure existing frontend/backend health consumers tolerate the shape.
- [ ] Document readiness semantics.

**Verification:**

- [ ] Test API role readiness with scheduler disabled.
- [ ] Test scheduler role readiness with scheduler enabled.
- [ ] Test DB/Alembic failure still returns 503.

**Definition of Done:**

- `/ready` is correct for API-only and scheduler-enabled roles.

---

## Task 4: Harden Scheduled Job Execution

**Purpose:** Avoid duplicate or overlapping scheduled report execution.

**CodeGraph preflight:**

```powershell
codegraph node _run_scheduled_report
codegraph impact ScheduledReport --depth 3 --json
```

**Files:**

- Modify: `scada-reporter/backend/app/services/scheduler.py`
- Possibly modify: `scada-reporter/backend/app/models/scheduled_report.py`
- Add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Add job execution guard:
  - Minimum: skip when same scheduled report is already marked `running` and recent.
  - Better: use DB row lock where supported.
  - Optional later: PostgreSQL advisory lock.
- [ ] Add explicit status transitions:
  - `running`
  - `completed`
  - `failed`
  - optional `skipped`
- [ ] Store bounded error text.
- [ ] Update `next_run_at` reliably after success/failure.
- [ ] Add tests:
  - Success transition.
  - Failure transition.
  - Overlap guard.
  - Missing template behavior.

**Verification:**

- [ ] Run scheduler tests.
- [ ] Run advanced report API tests.

**Definition of Done:**

- A scheduled report cannot silently overlap itself.
- Failures are visible and bounded.

---

## Task 5: Add Scheduler API Tests

**Purpose:** Cover create/update/toggle/delete flows with role-aware scheduler behavior.

**CodeGraph preflight:**

```powershell
codegraph explore "advanced reports scheduled create update toggle remove_job register_job" --max-files 8
```

**Files:**

- Modify/add tests under `scada-reporter/backend/tests/`
- Likely target: `test_advanced_reports.py` or new `test_scheduled_reports.py`

**Steps:**

- [ ] Test create scheduled report with scheduler enabled.
- [ ] Test create scheduled report with scheduler disabled.
- [ ] Test update reschedules when enabled.
- [ ] Test toggle inactive removes job.
- [ ] Test toggle active registers job when scheduler enabled.
- [ ] Test behavior when scheduler disabled is explicit and documented.

**Verification:**

- [ ] Run only scheduled report tests.
- [ ] Run broader advanced report tests.

**Definition of Done:**

- CodeGraph no longer reports weak/no obvious test signal for scheduler paths after re-indexing.

---

## Task 6: Add Auth Regression Tests

**Purpose:** Cover the broad auth blast radius before changing token/session behavior.

**CodeGraph preflight:**

```powershell
codegraph impact authenticate_token --depth 3 --json
codegraph node authenticate_token
```

**Files:**

- Modify/add tests under `scada-reporter/backend/tests/`
- Possible new file: `test_auth_token_validation.py`

**Steps:**

- [ ] Test valid token returns active user.
- [ ] Test invalid token returns 401.
- [ ] Test inactive user returns 401.
- [ ] Test token version mismatch returns 401.
- [ ] Test unknown scope returns 401.
- [ ] Test SSE-scoped token rejected by normal API auth.
- [ ] Test SSE-scoped token accepted only when `sse_allowed=True`.
- [ ] Test expired token returns 401.

**Verification:**

- [ ] Run auth tests.
- [ ] Run realtime stream token tests.

**Definition of Done:**

- Auth validation behavior is directly covered.

---

## Task 7: Document and Tune Token Production Defaults

**Purpose:** Reduce production token exposure risk without forcing a disruptive auth rewrite.

**CodeGraph preflight:**

```powershell
codegraph explore "authentication frontend localStorage token axios interceptor logout" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/core/config.py`
- Modify: `scada-reporter/backend/.env.production.example`
- Modify: `docs/deployment.md`
- Optionally modify: frontend docs

**Steps:**

- [ ] Add production recommendation for shorter `ACCESS_TOKEN_EXPIRE_MINUTES`.
- [ ] Consider a config warning if production TTL is above a threshold.
- [ ] Document that bearer tokens are stored in browser localStorage today.
- [ ] Document HTTPS/CSP requirement.
- [ ] Create follow-up note for HttpOnly cookie evaluation.

**Verification:**

- [ ] Run config validation tests.
- [ ] Confirm docs use concrete env examples.

**Definition of Done:**

- Production auth risk is visible and configurable.

---

## Task 8: Harden Query Endpoint

**Purpose:** Preserve agent SQL discovery while preventing expensive or mutating queries.

**CodeGraph preflight:**

```powershell
codegraph node run_query
codegraph impact run_query --depth 3 --json
```

**Files:**

- Modify: `scada-reporter/backend/app/api/query.py`
- Modify: `scada-reporter/backend/app/core/config.py`
- Add tests under `scada-reporter/backend/tests/`
- Update CLI/agent docs if behavior changes

**Steps:**

- [ ] Add config:
  - `QUERY_MAX_ROWS`
  - `QUERY_MAX_SQL_CHARS`
  - `QUERY_STATEMENT_TIMEOUT_MS`
  - optional `QUERY_READONLY_DATABASE_URL`
- [ ] Reject multiple statements.
- [ ] Enforce maximum SQL length.
- [ ] Clamp `limit` to configured max.
- [ ] Push limit to SQL execution where practical.
- [ ] For PostgreSQL, set local `statement_timeout`.
- [ ] Prefer read-only connection/role if configured.
- [ ] Avoid `result.all()` for unbounded result sets.
- [ ] Add audit log entry without storing full SQL by default, or store a truncated/hash form.

**Verification:**

- [ ] Test mutating queries rejected.
- [ ] Test multi-statement rejected.
- [ ] Test max SQL length.
- [ ] Test limit clamping.
- [ ] Test timeout path where feasible.
- [ ] Test normal SELECT still works for CLI/agent use.

**Definition of Done:**

- Query endpoint has layered app and DB-level controls.

---

## Task 9: Add Upload Limit Utilities

**Purpose:** Centralize upload safety checks before endpoint-specific changes.

**CodeGraph preflight:**

```powershell
codegraph explore "UploadFile tags import excel templates license upload" --max-files 8
```

**Files:**

- Create: `scada-reporter/backend/app/core/upload_limits.py`
- Modify: `scada-reporter/backend/app/core/config.py`
- Add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Add configurable limits:
  - `UPLOAD_MAX_XLSX_BYTES`
  - `UPLOAD_MAX_CSV_BYTES`
  - `UPLOAD_MAX_LICENSE_BYTES`
  - `UPLOAD_MAX_TEMPLATE_B64_BYTES`
- [ ] Implement helper to read at most `limit + 1` bytes.
- [ ] Implement extension normalization.
- [ ] Implement magic-byte checks:
  - XLSX zip header.
  - CSV text fallback.
  - License text/JWT shape.
- [ ] Return controlled `HTTPException` errors.

**Verification:**

- [ ] Unit test helper accepts valid small payload.
- [ ] Unit test helper rejects oversized payload.
- [ ] Unit test helper rejects wrong magic bytes.

**Definition of Done:**

- Endpoints can share consistent upload safety behavior.

---

## Task 10: Apply Upload Hardening to Endpoints

**Purpose:** Protect import/template/license endpoints.

**CodeGraph preflight:**

```powershell
codegraph impact import_tags --depth 3 --json
codegraph impact import_tags_csv --depth 3 --json
codegraph impact inspect --depth 3 --json
codegraph impact upload_license --depth 3 --json
```

**Files:**

- Modify: `scada-reporter/backend/app/api/tags.py`
- Modify: `scada-reporter/backend/app/api/excel_templates.py`
- Modify: `scada-reporter/backend/app/api/license.py`
- Add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Replace raw `await file.read()` with upload limit helper.
- [ ] Add XLSX row/sheet/cell guard where parsing happens.
- [ ] Add CSV row-count guard.
- [ ] Add base64 decoded-size guard for template creation.
- [ ] Add clear error messages for oversize and malformed content.

**Verification:**

- [ ] Test oversized XLSX import.
- [ ] Test oversized CSV import.
- [ ] Test malformed XLSX.
- [ ] Test malformed license.
- [ ] Test oversized template base64 payload.
- [ ] Run existing import/template/license tests.

**Definition of Done:**

- Upload endpoints fail safely and consistently.

---

## Task 11: Decompose Report Generator Data Loading

**Purpose:** Split DB/data preparation from output rendering.

**CodeGraph preflight:**

```powershell
codegraph node generate_report_from_template
codegraph impact generate_report_from_template --depth 3 --json
```

**Files:**

- Modify: `scada-reporter/backend/app/services/report_generator.py`
- Add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Extract `load_report_tags`.
- [ ] Extract `load_tag_readings`.
- [ ] Extract `build_per_tag_report_data`.
- [ ] Keep behavior unchanged.
- [ ] Add unit tests for extracted pure/semi-pure helpers.

**Verification:**

- [ ] Run report generator tests.
- [ ] Run advanced report tests.

**Definition of Done:**

- Data loading and per-tag data construction are testable independently.

---

## Task 12: Decompose Report Output and Archive Persistence

**Purpose:** Isolate rendering, file writing, and archive state transitions.

**CodeGraph preflight:**

```powershell
codegraph explore "report output excel pdf json archive status file_path result_json" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/services/report_generator.py`
- Add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Extract `render_grafana_panels`.
- [ ] Extract `build_report_output`.
- [ ] Extract `write_report_file`.
- [ ] Extract `persist_archive_success`.
- [ ] Extract `persist_archive_failure`.
- [ ] Make report output object explicit:

```python
@dataclass
class ReportOutput:
    content: bytes
    extension: str
    summary: dict
```

**Verification:**

- [ ] Test success path sets file path, file size, status, completed time.
- [ ] Test failure path sets failed status and error.
- [ ] Test Grafana render failure remains tolerated.

**Definition of Done:**

- `generate_report_from_template` becomes a readable orchestrator.

---

## Task 13: Split Trend Frontend Page

**Purpose:** Reduce the largest frontend component first.

**CodeGraph preflight:**

```powershell
codegraph node Trend
codegraph explore "frontend Trend page trend chart tag selector annotations export" --max-files 8
```

**Files:**

- Modify: `scada-reporter/frontend/src/pages/Trend.tsx`
- Possibly create under `scada-reporter/frontend/src/pages/trend/`
- Add/modify tests

**Steps:**

- [ ] Extract query/data hook.
- [ ] Extract selection state hook.
- [ ] Extract export/context-menu logic.
- [ ] Extract annotation panel if not already isolated.
- [ ] Keep UI behavior unchanged.

**Verification:**

- [ ] Run frontend tests.
- [ ] Run TypeScript check.
- [ ] Run targeted Playwright/UI smoke if available.

**Definition of Done:**

- `Trend.tsx` is materially smaller and easier to scan.

---

## Task 14: Split Advanced Reports Page

**Purpose:** Reduce modal and tab complexity.

**CodeGraph preflight:**

```powershell
codegraph node TemplateEditorModal
codegraph explore "frontend AdvancedReports templates schedules archive modal" --max-files 8
```

**Files:**

- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
- Create components/hooks under a local folder
- Add/modify tests

**Steps:**

- [ ] Extract `TemplateEditorModal`.
- [ ] Extract `ScheduleCreateModal`.
- [ ] Extract `TemplatesTab`.
- [ ] Extract `ScheduledTab`.
- [ ] Extract `ArchiveTab`.
- [ ] Move shared formatting helpers to a helper module.

**Verification:**

- [ ] Run frontend tests.
- [ ] Run TypeScript check.
- [ ] Verify archive download and run-template flow still work.

**Definition of Done:**

- Advanced Reports page is split into clear components with preserved behavior.

---

## Task 15: Split Tags and Reports Pages

**Purpose:** Reduce remaining large operational pages.

**CodeGraph preflight:**

```powershell
codegraph node Tags
codegraph node Reports
```

**Files:**

- Modify: `scada-reporter/frontend/src/pages/Tags.tsx`
- Modify: `scada-reporter/frontend/src/pages/Reports.tsx`
- Create local component/helper files
- Add/modify tests

**Steps:**

- [ ] For `Tags`:
  - Extract add/edit/import/group modals.
  - Extract table/tree view switch.
  - Extract import/export helpers.
- [ ] For `Reports`:
  - Extract preset management hook.
  - Extract tag selection controls.
  - Extract date/interval controls.
  - Extract download action area.

**Verification:**

- [ ] Run frontend tests.
- [ ] Run TypeScript check.
- [ ] Smoke manually or with Playwright if existing flow coverage is weak.

**Definition of Done:**

- Major page components are below agreed complexity targets or have documented exceptions.

---

## Task 16: Consolidate Manual API Types

**Purpose:** Reduce drift between generated OpenAPI types and manual frontend types.

**CodeGraph preflight:**

```powershell
codegraph node scada-reporter/frontend/src/api/client.ts --file scada-reporter/frontend/src/api/client.ts --symbols-only
codegraph explore "frontend api client generated types manual types axios" --max-files 8
```

**Files:**

- Modify: `scada-reporter/frontend/src/api/client.ts`
- Possibly modify generated client configuration only through generator config
- Add/modify tests

**Steps:**

- [ ] Inventory manual interfaces in `client.ts`.
- [ ] Replace manual interfaces with generated re-exports where shapes match.
- [ ] Keep manual wrappers for:
  - Auth headers.
  - Binary downloads.
  - SSE token helper.
  - Shape mismatches with documented reason.
- [ ] Add comments only for intentional divergences.

**Verification:**

- [ ] Run `just contract-check`.
- [ ] Run TypeScript check.
- [ ] Run frontend tests.

**Definition of Done:**

- Manual type drift surface is smaller and intentional.

---

## Task 17: Add Agent Contract Check

**Purpose:** Protect CLI/MCP/SKILL surfaces used by coding agents.

**CodeGraph preflight:**

```powershell
codegraph explore "agent cli scada-core MCP server resources tools SKILL" --max-files 8
```

**Files:**

- Create: `scripts/agent-contract-check.ps1`
- Modify: `justfile`
- Add tests/snapshots under agent/MCP test folders as appropriate
- Update docs

**Steps:**

- [ ] Snapshot CLI command groups and representative subcommands.
- [ ] Smoke representative JSON commands with mocked or local backend where feasible.
- [ ] Snapshot MCP resource/tool names.
- [ ] Check `agent-harness/skills/SKILL.md` command references against CLI availability.
- [ ] Add `just agent-contract-check`.

**Verification:**

- [ ] Run `just agent-contract-check`.
- [ ] Confirm intentional command changes require snapshot/doc update.

**Definition of Done:**

- Agent-facing drift can be detected locally.

---

## Task 18: Document CodeGraph Review Workflow

**Purpose:** Make future architecture analysis repeatable.

**Files:**

- Create or update: `docs/codegraph-review.md`
- Update: `AGENTS.md` or developer docs if appropriate
- Possibly update: `docs/project-improvement-recommendations.md`

**Steps:**

- [ ] Document basic commands:
  - `codegraph status`
  - `codegraph sync`
  - `codegraph query`
  - `codegraph node`
  - `codegraph explore`
  - `codegraph impact`
- [ ] Document review recipes:
  - Scheduler/runtime review.
  - Auth/security review.
  - Report generation review.
  - Frontend complexity review.
  - Agent contract review.
- [ ] Document limitations:
  - Generated files can dominate metrics.
  - Some TypeScript imports may need text verification.
  - Always cross-check critical claims with source/tests.

**Verification:**

- [ ] Run documented commands.
- [ ] Confirm examples work on current repo.

**Definition of Done:**

- Maintainers can repeat the CodeGraph-based review without reconstructing the workflow.

---

## Task 19: Add Metrics for Hardened Boundaries

**Purpose:** Make new guardrails observable.

**CodeGraph preflight:**

```powershell
codegraph explore "metrics prometheus report scheduler upload query auth" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/core/metrics.py`
- Modify affected endpoints/services
- Add tests if metrics helpers are tested

**Steps:**

- [ ] Add scheduler job counters:
  - started
  - completed
  - failed
  - skipped
- [ ] Add report generation duration histogram.
- [ ] Add upload rejection counter by endpoint/reason.
- [ ] Add query timeout/rejection counter by reason.
- [ ] Add auth failure/rate-limit counter if not already present.
- [ ] Avoid high-cardinality labels.

**Verification:**

- [ ] Run metrics tests.
- [ ] Inspect `/metrics` locally or through unit tests.

**Definition of Done:**

- New safety controls are visible in Prometheus.

---

## Task 20: Final CodeGraph Re-Index and Review

**Purpose:** Confirm the hardening work reduced risk and did not introduce new dependency problems.

**Commands:**

```powershell
codegraph sync
codegraph status
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
codegraph explore "report generation scheduled report archive generate_report_from_template" --max-files 8
codegraph explore "authentication token get_current_user require_role permissions" --max-files 8
codegraph impact get_scheduler --depth 3 --json
codegraph impact authenticate_token --depth 3 --json
```

**Steps:**

- [ ] Compare scheduler blast radius before/after.
- [ ] Confirm no backend mutual import cycles were introduced.
- [ ] Confirm generated frontend files are excluded from complexity conclusions.
- [ ] Check largest hand-written frontend functions after decomposition.
- [ ] Check report generator function size and callers.
- [ ] Check tests cover new scheduler/auth/query/upload paths.

**Verification:**

- [ ] Run backend targeted tests.
- [ ] Run frontend targeted tests.
- [ ] Run `just contract-check`.
- [ ] Run `just agent-contract-check` if implemented.

**Definition of Done:**

- CodeGraph review supports the claim that architecture risk was reduced.

---

## Recommended Execution Order

1. Task 1: Add Scheduler Role Configuration
2. Task 2: Add Dedicated Scheduler Runner
3. Task 3: Make Readiness Role-Aware
4. Task 4: Harden Scheduled Job Execution
5. Task 5: Add Scheduler API Tests
6. Task 6: Add Auth Regression Tests
7. Task 7: Document and Tune Token Production Defaults
8. Task 8: Harden Query Endpoint
9. Task 9: Add Upload Limit Utilities
10. Task 10: Apply Upload Hardening to Endpoints
11. Task 11: Decompose Report Generator Data Loading
12. Task 12: Decompose Report Output and Archive Persistence
13. Task 13: Split Trend Frontend Page
14. Task 14: Split Advanced Reports Page
15. Task 15: Split Tags and Reports Pages
16. Task 16: Consolidate Manual API Types
17. Task 17: Add Agent Contract Check
18. Task 18: Document CodeGraph Review Workflow
19. Task 19: Add Metrics for Hardened Boundaries
20. Task 20: Final CodeGraph Re-Index and Review

The first ten tasks are correctness and security hardening. The next six are maintainability and drift reduction. The final tasks make the improvements observable and repeatable.

## Final Acceptance Checklist

- [ ] API workers can run with scheduler disabled.
- [ ] A dedicated scheduler process exists and is documented.
- [ ] Readiness is role-aware.
- [ ] Scheduled report jobs do not silently overlap or duplicate.
- [ ] Scheduler API behavior has direct tests.
- [ ] Auth token validation has direct tests.
- [ ] Production token risk is documented and configurable.
- [ ] Query endpoint has length, row, timeout, and read-only controls.
- [ ] Upload endpoints enforce size/type/content limits.
- [ ] Report generator orchestration is decomposed.
- [ ] Large frontend pages are split into smaller components/hooks.
- [ ] Manual frontend API type drift is reduced.
- [ ] Agent CLI/MCP/SKILL contract drift check exists.
- [ ] CodeGraph review workflow is documented.
- [ ] New guardrails emit useful metrics.
- [ ] Final CodeGraph review shows no new dependency cycles and reduced complexity in targeted areas.
