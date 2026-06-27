# CodeGraph Infrastructure Improvements — Design Spec

**Date:** 2026-06-27
**Status:** Proposed
**Scope:** Targeted infrastructure improvements based on a fresh CodeGraph review of the EKONT SMART REPORT repository. This spec focuses on runtime safety, authentication boundaries, report-generation maintainability, frontend/API contract drift, agent stability, and production packaging clarity.

## 1. Goal

Use CodeGraph findings to turn the remaining infrastructure risks into a small, prioritized improvement program.

The desired outcome is a platform where:

- Realtime streaming never exposes normal bearer tokens through query parameters.
- Scheduled report execution is protected from duplicate scheduler processes.
- Advanced report generation is easier to test and change.
- Agent-facing CLI/MCP contracts remain stable and machine-readable.
- Frontend API usage converges toward the generated OpenAPI client.
- Large frontend pages are split without changing user-facing behavior.
- Production deployment choices are explicit and verifiable.

## 2. CodeGraph Snapshot

The local CodeGraph index was current at review time:

| Metric | Value |
|---|---:|
| Files | 392 |
| Nodes | 6,558 |
| Edges | 13,965 |
| Status | Up to date |

Review commands:

```powershell
codegraph status
codegraph explore "backend startup scheduler collector database readiness flow" --max-files 8
codegraph explore "authentication token get_current_user require_role permissions stream token frontend token handling" --max-files 8
codegraph explore "report generation scheduled report archive generate_report_from_template grafana excel pdf" --max-files 8
codegraph explore "UploadFile tags import excel templates license upload query run SQL input validation row count file size" --max-files 10
codegraph explore "frontend large pages Trend AdvancedReports Tags Reports LabEntry generated client manual api client" --max-files 10
codegraph explore "agent cli scada-core MCP server resources tools SKILL doctor json-output" --max-files 10
codegraph impact authenticate_token --depth 3 --json
codegraph impact generate_report_from_template --depth 3 --json
codegraph impact run_query --depth 3 --json
codegraph impact SyncScadaClient --depth 3 --json
```

Important impact results:

- `authenticate_token` affects 41 nodes across core API auth, realtime streams, lab, Grafana, dashboard, tags, license, and tests.
- `generate_report_from_template` affects 10 nodes, but it concentrates many responsibilities in one function.
- `run_query` affects only 1 node, making it a good candidate for isolated hardening.
- `SyncScadaClient` is covered by `test_sync_facade.py`, including multi-call event loop behavior.

## 3. Current State

The repository already has several mature infrastructure controls:

- Python 3.14 is the declared baseline across backend, CLI, and `scada-core`.
- `just check` covers backend, frontend, CLI, MCP, and generated OpenAPI contract freshness.
- `/live`, `/ready`, and `/health` exist with role-aware scheduler readiness.
- Production config validation blocks several unsafe defaults and warns on risky combinations.
- Backend query guardrails include SQL length caps, single-statement detection, row caps, bounded fetches, and statement timeout.
- Generated frontend OpenAPI files are committed and contract freshness is checked.
- Agent CLI includes `scada doctor --json-output`.
- MCP and CLI agent contract tests exist.

The remaining work is not a broad rewrite. It is a set of focused improvements around still-visible risk concentrations.

## 4. Non-Goals

- Do not replace FastAPI, React, APScheduler, Click, FastMCP, or CodeGraph.
- Do not manually edit generated OpenAPI files.
- Do not redesign the frontend while splitting components.
- Do not move the whole deployment model to Docker unless explicitly approved.
- Do not remove local development conveniences.
- Do not merge unrelated feature work into these infrastructure tasks.

## 5. Design Principles

| Principle | Implication |
|---|---|
| Reduce exposed credentials first | Streaming auth changes should precede cosmetic or structural cleanup. |
| Make runtime topology enforceable | Scheduler single-instance assumptions should become detectable or locked. |
| Split IO from computation | Report generation should isolate data collection, rendering, output building, and persistence. |
| Prefer contract tests for agent surfaces | CLI/MCP JSON outputs should be protected by schema or snapshot tests. |
| Treat generated code as generated | Maintainability conclusions should focus on handwritten wrappers and pages. |
| Keep each change narrow | Every task starts with CodeGraph and ends with targeted tests. |

## 6. Proposed Improvements

### 6.1 Realtime Stream Token Boundary

Current realtime endpoints accept a `token` query parameter and call `authenticate_token(..., sse_allowed=True)`. A short-lived stream token model exists, but the stream endpoints should reject normal access tokens when the token travels through the URL.

Proposed behavior:

- `/api/auth/stream-token` remains the only way to mint stream tokens.
- `/api/dashboard/stream` accepts only a stream-scoped token.
- `/api/dashboard/logs/stream` accepts only a stream-scoped token.
- Normal bearer access tokens continue to work for non-SSE APIs through the `Authorization` header.
- Frontend stream hooks fetch a stream token and renew it before or after expiry.

Success criteria:

- Normal access token in SSE query string is rejected.
- Stream-scoped token is accepted only for stream endpoints.
- Existing auth token validation tests remain green.
- Frontend stream behavior is covered by hook or utility tests.

### 6.2 Scheduler Single-Instance Guard

The production documentation defines a single scheduler process, but the runtime should make duplicate scheduler starts visible or impossible.

Preferred approach:

- Add a database-backed advisory lock or equivalent scheduler ownership guard for PostgreSQL.
- For SQLite or tests, use a no-op or process-local fallback.
- Expose ownership state in `/ready` or `/health`.
- Fail scheduler startup clearly when another scheduler owns the lock.

Success criteria:

- Starting a second scheduler process fails or reports not-ready instead of silently registering duplicate jobs.
- API workers with `RUN_SCHEDULER=False` are unaffected.
- Scheduler tests cover lock acquisition and duplicate-start behavior.

### 6.3 Report Generator Decomposition

`generate_report_from_template` currently performs archive state transitions, tag data loading, statistics, anomaly detection, trend charts, Grafana rendering, output building, file writing, and DB persistence.

Proposed module boundaries:

- `collect_report_data(template, start, end, db)` loads tags and readings.
- `build_report_dataset(...)` computes stats, anomalies, aggregates, and chart inputs.
- `render_report_assets(...)` handles chart and Grafana PNG generation.
- `build_report_output(...)` creates Excel/PDF/JSON bytes and extension.
- `persist_report_output(...)` writes files and updates archive metadata.
- `generate_report_from_template(...)` remains the orchestration entrypoint for API and scheduler callers.

Success criteria:

- Existing report tests still call the public orchestration function.
- New unit tests cover at least one pure helper without DB or Grafana.
- Grafana render failure tolerance is preserved.

### 6.4 Query Endpoint Audit and Parser Hardening

The query endpoint is already isolated and guarded. The next step is to add evidence and reduce parser edge cases.

Options:

- Add regression tests for CTE write attempts such as `WITH x AS (DELETE ... RETURNING ...) SELECT ...`.
- Add audit logging for every query attempt with user ID, SQL length, effective limit, result status, and truncation flag.
- Consider a SQL parser allowlist if regex scanning becomes hard to reason about.

Success criteria:

- Write-capable CTE attempts are rejected.
- Query attempts are observable without storing full sensitive SQL by default.
- Limits and truncation remain visible in API responses.

### 6.5 Frontend API Client Convergence

The frontend has both generated OpenAPI client files and a handwritten `src/api/client.ts`. The handwritten wrapper should become a compatibility adapter, not a parallel API contract.

Proposed direction:

- Keep handwritten axios config, auth interceptor, and compatibility wrappers.
- Move new endpoint usage to generated SDK functions where practical.
- Remove duplicated manual interfaces after call sites migrate.
- Keep `just contract-check` as the drift gate.

Success criteria:

- New API work uses generated types by default.
- Manual types shrink over time.
- Frontend tests do not depend on generated internals directly.

### 6.6 Frontend Page Decomposition

`AdvancedReports.tsx` and other large pages mix fetching, mutations, table rendering, modals, sorting, and download behavior.

Decomposition target:

- Extract tab components into files.
- Extract API query/mutation hooks where repeated.
- Extract pure formatting and payload helpers into unit-tested modules.
- Preserve route behavior, translations, permissions, and visual layout.

Success criteria:

- No visible behavior change.
- Existing Vitest tests remain green.
- New helper tests cover extracted pure logic.

### 6.7 Agent Contract Stability

Agent surfaces are first-class product interfaces. `scada doctor --json-output`, MCP resources, and `scada-core` should be treated as contracts.

Proposed controls:

- Add JSON schema or snapshot tests for `doctor --json-output`.
- Add a contract fixture for MCP tag/resource/prompt discovery.
- Keep `scada-core` sync facade tests, including multi-call behavior.
- Document output compatibility expectations in `agent-harness/skills/SKILL.md`.

Success criteria:

- Breaking JSON field changes fail tests.
- `just agent-check` remains the local smoke gate.
- Agent docs match CLI behavior.

### 6.8 Production Packaging Clarity

The current deployment guide favors native OS process deployment. Docker compose is infrastructure-only by design.

Recommended choice:

- Either add application Dockerfiles and compose services for API, scheduler, collector, and frontend.
- Or explicitly mark compose as infrastructure-only and keep native service files as the production path.

Success criteria:

- Operators can tell which production topology is supported.
- No one assumes `docker-compose.yml` starts the full app.
- Deployment docs and compose comments agree.

### 6.9 CodeGraph Release Review

CodeGraph should remain part of the maintenance loop without making every CI run heavy.

Proposed controls:

- Add release checklist commands to `docs/codegraph-review.md`.
- Optionally add a manual CI job that runs `codegraph status` and selected `impact` commands.
- Require CodeGraph preflight in implementation plan tasks for high-blast-radius files.

Success criteria:

- Maintainers can repeat the review.
- High-risk changes include CodeGraph context in the task or PR.

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Stream-token-only SSE breaks existing clients | Add transition notes and frontend migration in the same task. |
| Scheduler lock behaves differently on SQLite and PostgreSQL | Keep PostgreSQL lock production-only and test fallback behavior separately. |
| Report decomposition changes behavior | Preserve public function signature and run existing report tests after each extraction. |
| Generated client migration causes broad frontend churn | Migrate endpoint families incrementally, not all at once. |
| Component splitting creates visual regressions | Keep CSS/classes unchanged and use existing page tests first. |

## 8. Verification Strategy

Minimum verification per area:

- Auth/realtime: `pytest tests/test_auth_token_validation.py tests/test_realtime.py`
- Scheduler: scheduler execution/readiness tests.
- Reports: report generator and Grafana report tests.
- Query: query endpoint tests.
- Frontend: targeted Vitest files plus `pnpm tsc --noEmit`.
- Agent: `just agent-check`.
- Full gate before merge: `just check`.

## 9. Recommended Implementation Order

1. Realtime stream token boundary.
2. Scheduler single-instance guard.
3. Query audit and edge-case hardening.
4. Report generator decomposition.
5. Agent contract schema/snapshot tests.
6. Frontend API client convergence.
7. Frontend page decomposition.
8. Production packaging clarity.
9. CodeGraph release-review checklist.
