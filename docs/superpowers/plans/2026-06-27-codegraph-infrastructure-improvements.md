# CodeGraph Infrastructure Improvements Implementation Plan

> **For agentic workers:** implement task-by-task. Start each task with the listed CodeGraph preflight command, make a narrow change, and verify with targeted tests. This plan is based on `docs/superpowers/specs/2026-06-27-codegraph-infrastructure-improvements-design.md`.

**Goal:** Reduce the remaining infrastructure risks identified by the latest CodeGraph review: realtime token exposure, scheduler duplication, report generator complexity, query observability, API client drift, frontend component size, agent contract drift, and production packaging ambiguity.

**Architecture:** Keep the current FastAPI backend, React/Vite frontend, APScheduler runtime, Click agent CLI, FastMCP server, `scada-core` boundary, generated OpenAPI client, and process-based deployment model unless a task explicitly changes documentation.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, APScheduler, pytest, React 19, Vite, TypeScript, Vitest, Click, FastMCP, CodeGraph CLI.

## Global Constraints

- Use CodeGraph before editing high-blast-radius symbols.
- Do not manually edit generated OpenAPI files.
- Do not change user-facing UI behavior during component decomposition.
- Do not remove the agent-native CLI/MCP surface.
- Keep API, scheduler, and collector roles explicit.
- Keep changes small and independently testable.
- Preserve local development convenience unless production safety requires a warning or explicit opt-in.

---

## Task 1: Enforce Stream-Scoped Tokens for SSE

**Purpose:** Prevent normal bearer access tokens from being passed through SSE query parameters.

**CodeGraph preflight:**

```powershell
codegraph impact authenticate_token --depth 3 --json
codegraph explore "authentication token get_current_user require_role permissions stream token frontend token handling" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/api/auth.py`
- Modify: `scada-reporter/backend/app/api/realtime.py`
- Modify: frontend stream hook or API utility files under `scada-reporter/frontend/src/`
- Add/modify backend tests under `scada-reporter/backend/tests/`
- Add/modify frontend tests if stream token helper logic changes

**Steps:**

- [ ] Identify how stream tokens are minted and validated.
- [ ] Add or expose a validation path that accepts only stream-scoped tokens.
- [ ] Change `/api/dashboard/stream` to reject normal access tokens in the query string.
- [ ] Change `/api/dashboard/logs/stream` the same way.
- [ ] Update frontend stream code to request and use stream tokens.
- [ ] Ensure stream token renewal or failure handling is explicit.
- [ ] Update docs if users call stream endpoints directly.

**Verification:**

- [ ] Normal access token in SSE query returns 401.
- [ ] Stream token in SSE query succeeds.
- [ ] Stream token is rejected by normal API auth.
- [ ] Existing auth tests pass.
- [ ] Relevant frontend stream tests pass.

**Definition of Done:**

- Long-lived bearer tokens are no longer accepted as SSE query credentials.
- Frontend realtime streams still connect.
- Token scope behavior is covered by tests.

---

## Task 2: Add Scheduler Single-Instance Guard

**Purpose:** Make duplicate scheduler processes impossible or visibly unhealthy in production.

**CodeGraph preflight:**

```powershell
codegraph impact get_scheduler --depth 3 --json
codegraph node start_scheduler
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/services/scheduler.py`
- Modify: `scada-reporter/backend/app/api/health.py`
- Modify: scheduler runner files under `scada-reporter/backend/app/scheduler/`
- Add/modify tests under `scada-reporter/backend/tests/`
- Update: `docs/deployment.md`

**Steps:**

- [ ] Choose a production lock mechanism, preferably PostgreSQL advisory lock.
- [ ] Add a small scheduler ownership abstraction.
- [ ] Acquire ownership before starting APScheduler.
- [ ] Fail startup or mark readiness not-ready when ownership cannot be acquired.
- [ ] Release ownership on clean shutdown where practical.
- [ ] Preserve SQLite/test fallback behavior.
- [ ] Expose lock/owner state in health or readiness output.
- [ ] Document the single-scheduler guarantee.

**Verification:**

- [ ] Unit test lock acquisition success.
- [ ] Unit test duplicate lock failure.
- [ ] Readiness reports unhealthy or startup fails when ownership is unavailable.
- [ ] API worker with `RUN_SCHEDULER=False` remains healthy when DB is ready.

**Definition of Done:**

- Duplicate scheduler processes cannot silently register duplicate jobs.
- Operators can see scheduler ownership state.

---

## Task 3: Add Query Audit and Edge-Case Tests

**Purpose:** Improve query endpoint observability and verify read-only enforcement edge cases.

**CodeGraph preflight:**

```powershell
codegraph impact run_query --depth 3 --json
codegraph node run_query
```

**Files:**

- Modify: `scada-reporter/backend/app/api/query.py`
- Modify/add: `scada-reporter/backend/tests/test_query.py`
- Modify audit model/service tests only if audit integration is reused

**Steps:**

- [ ] Add tests for write-capable CTE attempts.
- [ ] Add tests for semicolons in strings/comments if not already covered.
- [ ] Add audit logging for query attempts.
- [ ] Avoid storing full SQL by default; store length, user ID, status, limit, truncation, and optionally a short hash.
- [ ] Preserve existing response shape.

**Verification:**

- [ ] Query endpoint tests pass.
- [ ] Rejected write attempts are audited.
- [ ] Successful truncated queries report truncation and audit metadata.

**Definition of Done:**

- Query usage is observable.
- Read-only enforcement has regression coverage for known tricky SQL shapes.

---

## Task 4: Decompose Report Generation

**Purpose:** Reduce complexity in `generate_report_from_template` without changing public behavior.

**CodeGraph preflight:**

```powershell
codegraph impact generate_report_from_template --depth 3 --json
codegraph node generate_report_from_template
codegraph explore "report generation scheduled report archive generate_report_from_template grafana excel pdf" --max-files 8
```

**Files:**

- Modify: `scada-reporter/backend/app/services/report_generator.py`
- Optionally add helper module under `scada-reporter/backend/app/services/`
- Modify/add tests under `scada-reporter/backend/tests/`

**Steps:**

- [ ] Preserve `generate_report_from_template(...)` signature.
- [ ] Extract tag/readings collection into a helper.
- [ ] Extract stats/anomaly/period dataset building into a helper.
- [ ] Extract Grafana/chart asset rendering into a helper.
- [ ] Extract output bytes generation into a helper.
- [ ] Extract archive persistence into a helper.
- [ ] Add unit tests for at least one pure helper.
- [ ] Keep Grafana render failure behavior unchanged.

**Verification:**

- [ ] `pytest tests/test_report_generator.py tests/test_report_generator_grafana.py`
- [ ] Scheduler execution tests that call report generation pass.
- [ ] No archive response shape changes.

**Definition of Done:**

- The orchestration function is smaller and delegates testable responsibilities.
- Existing report behavior remains stable.

---

## Task 5: Add Agent Contract Schema or Snapshot Tests

**Purpose:** Protect machine-readable agent outputs from accidental breaking changes.

**CodeGraph preflight:**

```powershell
codegraph explore "agent cli scada-core MCP server resources tools SKILL doctor json-output" --max-files 10
codegraph impact SyncScadaClient --depth 3 --json
```

**Files:**

- Modify/add: `scada-reporter/agent-harness/tests/test_cli.py`
- Modify/add: `mcp-servers/mcp-scada/tests/test_agent_contract.py`
- Modify: `scada-reporter/agent-harness/skills/SKILL.md` if contract text changes

**Steps:**

- [ ] Define required fields for `scada doctor --json-output`.
- [ ] Add a schema-style assertion or stable snapshot fixture.
- [ ] Add MCP resource/prompt/tool contract assertions if missing.
- [ ] Verify `SyncScadaClient` multi-call behavior remains covered.
- [ ] Document compatibility expectations for JSON fields.

**Verification:**

- [ ] `just agent-check`
- [ ] Agent harness tests pass.
- [ ] MCP tests pass.

**Definition of Done:**

- Breaking doctor/MCP output changes fail tests.
- Agent docs match the tested contract.

---

## Task 6: Start Frontend API Client Convergence

**Purpose:** Reduce drift between generated OpenAPI types and handwritten frontend API wrappers.

**CodeGraph preflight:**

```powershell
codegraph explore "frontend api client generated types manual types axios" --max-files 10
codegraph node scada-reporter/frontend/src/api/client.ts --file scada-reporter/frontend/src/api/client.ts --symbols-only
```

**Files:**

- Modify: `scada-reporter/frontend/src/api/client.ts`
- Modify selected call sites under `scada-reporter/frontend/src/pages/` or `src/hooks/`
- Do not manually edit: `scada-reporter/frontend/src/api/generated/`

**Steps:**

- [ ] Pick one endpoint family with low UI risk.
- [ ] Replace duplicated manual types with generated types where practical.
- [ ] Keep axios configuration and auth behavior stable.
- [ ] Add a compatibility wrapper if call sites expect old response shape.
- [ ] Run contract generation through existing commands rather than manual edits.

**Verification:**

- [ ] `just contract-check`
- [ ] `cd scada-reporter/frontend && pnpm tsc --noEmit`
- [ ] Targeted Vitest tests for touched pages/hooks.

**Definition of Done:**

- One endpoint family is generated-type-backed.
- Manual client surface shrinks or becomes a thinner adapter.

---

## Task 7: Decompose Advanced Reports Page

**Purpose:** Split a large frontend page into smaller modules without changing behavior.

**CodeGraph preflight:**

```powershell
codegraph node AdvancedReports
codegraph explore "frontend AdvancedReports templates schedules archive modal" --max-files 10
```

**Files:**

- Modify: `scada-reporter/frontend/src/pages/AdvancedReports.tsx`
- Add components/hooks under `scada-reporter/frontend/src/pages/advancedReports/` or an existing local convention
- Modify/add tests under `scada-reporter/frontend/src/pages/`

**Steps:**

- [ ] Extract `TemplatesTab`.
- [ ] Extract `ScheduledTab`.
- [ ] Extract `ArchiveTab`.
- [ ] Extract pure formatting or payload helpers if useful.
- [ ] Keep CSS classes, translation keys, and permissions unchanged.
- [ ] Add unit tests for extracted pure helpers.

**Verification:**

- [ ] Existing `AdvancedReports` tests pass.
- [ ] `pnpm tsc --noEmit` passes.
- [ ] No generated files are manually changed.

**Definition of Done:**

- `AdvancedReports.tsx` becomes a route shell.
- Extracted modules preserve current UI behavior.

---

## Task 8: Clarify Production Packaging Decision

**Purpose:** Remove ambiguity about whether Docker compose runs only infrastructure or the full application.

**CodeGraph preflight:**

```powershell
codegraph explore "docker compose deployment api collector scheduler frontend production topology" --max-files 8
```

**Files:**

- Modify: `scada-reporter/docker/docker-compose.yml`
- Modify: `docs/deployment.md`
- Modify: `DOCKER.md` if it describes application deployment
- Optionally add Dockerfiles only if the team chooses containerized application deployment

**Steps:**

- [ ] Decide whether the supported production path is native services or app containers.
- [ ] If native services remain primary, label compose as infrastructure-only in comments and docs.
- [ ] If app containers are in scope, add separate services for API, scheduler, collector, and frontend.
- [ ] Ensure role env vars are correct for each process.
- [ ] Document health/readiness endpoints for the chosen topology.

**Verification:**

- [ ] Docs and compose comments do not contradict each other.
- [ ] Operators can identify how to start API, scheduler, collector, and frontend.

**Definition of Done:**

- Deployment topology is explicit.
- Docker compose is no longer easy to misread as a full app stack unless it actually is one.

---

## Task 9: Add CodeGraph Release Review Checklist

**Purpose:** Make future architecture reviews repeatable and lightweight.

**CodeGraph preflight:**

```powershell
codegraph status
codegraph explore "metrics prometheus report scheduler upload query auth agent frontend api client" --max-files 8
```

**Files:**

- Modify: `docs/codegraph-review.md`
- Optionally modify release checklist docs if present
- Optionally add manual CI workflow only if maintainers want it

**Steps:**

- [ ] Add a release review command block.
- [ ] Include high-risk impact commands for auth, scheduler, report generation, query, and agent contracts.
- [ ] Document how to interpret generated frontend files in graph output.
- [ ] Add a short PR checklist item for high-blast-radius changes.

**Verification:**

- [ ] Commands in docs run locally.
- [ ] The checklist references current file paths and command names.

**Definition of Done:**

- Maintainers can repeat the CodeGraph review without rediscovering commands.
- High-risk areas have a documented review loop.

---

## Final Verification

Run the broad gate after the selected tasks are complete:

```powershell
just check
just agent-check
codegraph sync
codegraph status
```

Expected result:

- Tests and contract checks pass.
- CodeGraph index is current.
- No generated OpenAPI drift remains.
- Agent CLI and MCP contract tests remain green.
