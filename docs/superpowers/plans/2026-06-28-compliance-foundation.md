# Compliance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working Compliance Center foundation: data model, deterministic evaluation engine, backend API, and agent-readable compliance overview/events.

**Architecture:** Add a bounded `compliance` backend slice that reads existing `tags`, `tag_readings`, `lab_*`, users, and audit tables without changing existing reporting behavior. Phase 1 deliberately excludes frontend screens and official report-pack rendering; it creates the durable domain model and engine that later phases depend on.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async ORM, Alembic, pytest-asyncio, existing `scada-core` capability catalog, Click-based agent CLI, FastMCP.

---

## Execution Rules

- Start implementation from an isolated worktree or explicit non-master branch before touching production code.
- Use TDD for every behavior change: write failing tests, verify failure, implement, verify pass.
- Keep commits per task.
- Do not modify generated frontend OpenAPI files manually.
- Do not implement UI/report-pack rendering in this plan.
- Do not alter existing Lab Data Entry, Advanced Reports, Grafana, or scheduler behavior except where compliance code imports shared models.

## Scope Boundary

This plan implements:

- Compliance ORM models and Alembic migration.
- Deterministic event key and event upsert behavior.
- Core evaluation for SCADA instant max/min, sample count, bad quality, and lab/hybrid missing-sample behavior.
- Compliance API for overview, permits, parameters, limits, events, notes, and manual evaluation.
- Read-oriented CLI and MCP capabilities for overview/events.

This plan does not implement:

- Report pack PDF/Excel/JSON generation.
- Approval workflow.
- Frontend Compliance Center route.
- AI Compliance Assistant.
- Email, e-signature, or government portal integration.

## File Structure

Create:

- `scada-reporter/backend/app/models/compliance.py`
  SQLAlchemy models for permits, discharge points, parameters, limits, events, event notes.

- `scada-reporter/backend/app/services/compliance_engine.py`
  Deterministic compliance evaluation service and event upsert helpers.

- `scada-reporter/backend/app/api/compliance.py`
  FastAPI router for CRUD, events, notes, overview, and evaluation.

- `scada-reporter/backend/tests/test_compliance_models.py`
  Model constraints and relationship smoke tests.

- `scada-reporter/backend/tests/test_compliance_engine.py`
  Unit-level engine tests using in-memory SQLite fixtures.

- `scada-reporter/backend/tests/test_compliance_api.py`
  API and permission tests.

- `scada-reporter/agent-harness/src/scada_reporter_cli/commands/compliance.py`
  CLI read commands and manual evaluate command.

Modify:

- `scada-reporter/backend/app/main.py`
  Task 1 imports compliance models only. Task 3 imports and includes the compliance router.

- `scada-reporter/backend/app/models/__init__.py` if present/needed.

- `scada-reporter/packages/scada-core/src/scada_core/endpoints.py`
  Add compliance endpoint constants.

- `scada-reporter/packages/scada-core/src/scada_core/client.py`
  Add compliance client methods.

- `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
  Add compliance read/write capabilities.

- `scada-reporter/agent-harness/src/scada_reporter_cli/cli.py`
  Register compliance command group.

- `mcp-servers/mcp-scada/src/mcp_scada/server.py`
  Add typed MCP functions for compliance read tools and write-gated evaluate.

- `scada-reporter/agent-harness/skills/SKILL.md` and root `AGENTS.md`
  Document new agent-facing commands.

## Task 1: Models and Migration

**Files:**
- Create: `scada-reporter/backend/app/models/compliance.py`
- Modify: `scada-reporter/backend/app/main.py`
- Create: `scada-reporter/backend/tests/test_compliance_models.py`
- Create: `scada-reporter/backend/alembic/versions/<revision>_add_compliance_tables.py`

- [ ] Write failing model metadata test.

Create `scada-reporter/backend/tests/test_compliance_models.py`:

```python
from app.models.compliance import ComplianceEvent, ComplianceLimit, CompliancePermit


def test_compliance_table_names_are_stable():
    assert CompliancePermit.__tablename__ == "compliance_permits"
    assert ComplianceLimit.__tablename__ == "compliance_limits"
    assert ComplianceEvent.__tablename__ == "compliance_events"


def test_event_key_is_unique_constraint():
    names = {c.name for c in ComplianceEvent.__table__.constraints}
    assert "uq_compliance_events_event_key" in names
```

- [ ] Run red test.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_models.py -q
```

Expected: fails because `app.models.compliance` does not exist.

- [ ] Implement ORM models.

Create `app/models/compliance.py` with:

- `CompliancePermit`
- `ComplianceDischargePoint`
- `ComplianceParameter`
- `ComplianceLimit`
- `ComplianceEvent`
- `ComplianceEventNote`

Required constants:

```python
REPORT_FREQUENCIES = ("daily", "weekly", "monthly", "quarterly", "custom_cron")
SOURCE_TYPES = ("scada", "lab", "hybrid")
LIMIT_TYPES = ("value_limit", "sample_count", "sample_frequency", "quality")
AGGREGATIONS = ("instant", "daily_avg", "monthly_avg", "count")
EVENT_TYPES = ("limit_exceeded", "missing_sample", "late_sample", "bad_quality", "needs_explanation")
EVENT_STATUSES = ("open", "acknowledged", "resolved", "waived")
```

Required model details:

- `ComplianceEvent.event_key` is `String(128)`, non-null, unique constraint name `uq_compliance_events_event_key`.
- `ComplianceLimit.requires_explanation` is boolean default false.
- `CompliancePermit.report_cron` is nullable string.
- `ComplianceParameter` keeps `permit_id` and `discharge_point_id`; API must later validate they match.
- DB-level composite constraints enforce that `ComplianceParameter.permit_id` matches its discharge point permit, and that `ComplianceEvent.permit_id`, `parameter_id`, and `limit_id` refer to one consistent graph.
- Parent records use explicit restrict semantics for Phase 1; do not cascade-delete legal compliance records when deleting permits, points, parameters, limits, events, or event notes.
- Event transition columns include `acknowledged_by/at`, `resolved_by/at`, `waived_by/at`, `waive_reason`.

- [ ] Import models into app startup.

Modify `app/main.py` to import compliance models near other `app.models` imports:

```python
from app.models import compliance as _compliance  # noqa: F401
from app.api import compliance
...
app.include_router(compliance.router, prefix="/api")
```

Do not import the compliance router in Task 1. Task 1 only imports models so metadata and tests can see the tables. The real router is created and mounted in Task 3.

- [ ] Create Alembic migration.

Use Alembic conventions already in `scada-reporter/backend/alembic/versions/`. The migration must create all six tables and indexes for:

- `compliance_events.status`
- `compliance_events.period_start`
- `compliance_events.permit_id`
- `compliance_parameters.permit_id`
- `compliance_limits.compliance_parameter_id`

Do not add a separate non-unique index on `compliance_events.event_key`; the unique constraint already backs lookup.

- [ ] Ensure Alembic autogenerate sees the models.

Modify `scada-reporter/backend/alembic/env.py` to import `app.models.compliance` near the other model imports.

- [ ] Run green tests.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_models.py -q
```

Expected: 2 passed.

- [ ] Commit.

```powershell
git add scada-reporter/backend/app/models/compliance.py scada-reporter/backend/app/main.py scada-reporter/backend/alembic/versions scada-reporter/backend/tests/test_compliance_models.py
git commit -m "feat(compliance): add foundation models"
```

## Task 2: Deterministic Compliance Engine

**Files:**
- Create: `scada-reporter/backend/app/services/compliance_engine.py`
- Create: `scada-reporter/backend/tests/test_compliance_engine.py`

- [ ] Write failing test for deterministic event upsert.

Create test data with one permit, point, scada parameter, `value_limit` max 10, and one `TagReading(value=12, quality=192)`.

Test:

```python
async def test_evaluate_upserts_limit_event(db_session):
    result1 = await evaluate_permit(db_session, permit.id, start, end)
    result2 = await evaluate_permit(db_session, permit.id, start, end)
    assert result1["created"] == 1
    assert result2["created"] == 0
    assert result2["updated"] == 1
    events = (await db_session.execute(select(ComplianceEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "limit_exceeded"
```

- [ ] Write failing test for hybrid lab authority.

Create a hybrid parameter with a required `sample_count` limit and SCADA readings but no lab measurement.

Expected:

```python
assert event.event_type == "missing_sample"
assert event.status == "open"
assert event.evidence_json contains "provisional_scada"
```

The engine must not create a compliant/closed event from SCADA fallback.

- [ ] Write failing test for bad quality.

Create a reading with `quality=0`; expect one `bad_quality` event.

- [ ] Run red tests.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_engine.py -q
```

Expected: fails because `app.services.compliance_engine` does not exist.

- [ ] Implement minimal engine.

Create public functions:

```python
async def evaluate_permit(db: AsyncSession, permit_id: int, period_start: datetime, period_end: datetime) -> dict[str, int]:
    ...

def build_event_key(permit_id: int, parameter_id: int, limit_id: int, event_type: str, period_start: datetime, period_end: datetime) -> str:
    ...
```

Implementation requirements:

- Normalize aware datetimes to naive UTC using existing `app.core.timeutils` helpers where practical.
- Query active permit parameters and limits.
- For `value_limit` + `scada`, evaluate raw instant readings for `aggregation="instant"` in Phase 1.
- For `sample_count` + `lab` or `hybrid`, count `lab_measurements` joined through `lab_samples` by point and parameter.
- For `quality`, create `bad_quality` when `TagReading.quality < 192`.
- Build `evidence_json` as compact JSON with source, counts, values, and rule metadata.
- Upsert by `event_key`: insert if absent, update evidence/value/severity/status timestamps if present.
- Create/resolve `needs_explanation` events when `ComplianceLimit.requires_explanation` is true and source event has/no notes.

- [ ] Run green tests.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_engine.py -q
```

Expected: all tests pass.

- [ ] Commit.

```powershell
git add scada-reporter/backend/app/services/compliance_engine.py scada-reporter/backend/tests/test_compliance_engine.py
git commit -m "feat(compliance): add evaluation engine"
```

## Task 3: Backend Compliance API

**Files:**
- Create: `scada-reporter/backend/app/api/compliance.py`
- Modify: `scada-reporter/backend/app/main.py`
- Create: `scada-reporter/backend/tests/test_compliance_api.py`

- [ ] Write failing API tests.

Tests:

- admin can create permit with `report_frequency="monthly"`.
- operator cannot create permit.
- operator can run `POST /api/compliance/evaluate`.
- authenticated user can list events.
- posting first note to a source event resolves related `needs_explanation`.

Use existing login helper pattern from `test_annotations.py`.

- [ ] Run red tests.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_api.py -q
```

Expected: fails because `/api/compliance/*` routes do not exist.

- [ ] Implement schemas and router.

Router prefix:

```python
router = APIRouter(prefix="/compliance", tags=["compliance"])
```

Minimum Phase 1 endpoints:

- `GET /overview`
- `GET /permits`
- `POST /permits` admin only
- `GET /events`
- `GET /events/{event_id}`
- `POST /events/{event_id}/notes` operator/admin
- `PATCH /events/{event_id}/status` operator/admin with role rules
- `POST /evaluate` operator/admin

Validation:

- `report_frequency` must be one of the spec values.
- `custom_cron` returns 422 or 400 in Phase 1 unless `report_cron` is supplied and scheduler support is explicitly implemented.
- `waived` transition requires non-empty `waive_reason`.

Audit:

- `compliance.permit.create`
- `compliance.evaluate`
- `compliance.event.note`
- `compliance.event.status`

- [ ] Mount router.

Modify `app/main.py`:

```python
from app.api import compliance
...
app.include_router(compliance.router, prefix="/api")
```

- [ ] Run green API tests.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_api.py -q
```

Expected: all tests pass.

- [ ] Commit.

```powershell
git add scada-reporter/backend/app/api/compliance.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_compliance_api.py
git commit -m "feat(compliance): expose backend API"
```

## Task 4: Agent CLI and MCP Read Surface

**Files:**
- Modify: `scada-reporter/packages/scada-core/src/scada_core/endpoints.py`
- Modify: `scada-reporter/packages/scada-core/src/scada_core/client.py`
- Modify: `scada-reporter/packages/scada-core/src/scada_core/catalog.py`
- Create: `scada-reporter/agent-harness/src/scada_reporter_cli/commands/compliance.py`
- Modify: `scada-reporter/agent-harness/src/scada_reporter_cli/cli.py`
- Modify: `mcp-servers/mcp-scada/src/mcp_scada/server.py`
- Modify tests under `scada-reporter/packages/scada-core/tests/`, `scada-reporter/agent-harness/tests/`, `mcp-servers/mcp-scada/tests/`

- [ ] Write failing core client/catalog tests.

Expected capabilities:

- `compliance_overview` tier `read`
- `compliance_list_events` tier `read`
- `compliance_evaluate` tier `write`

- [ ] Write failing CLI smoke test.

Use existing CLI tests pattern. Assert:

```powershell
scada compliance --help
scada compliance overview --json-output
```

The second command should call the mocked client and print JSON.

- [ ] Write failing MCP gating test.

Assert read compliance tools are registered by default and `compliance_evaluate` appears only with `SCADA_MCP_ALLOW_WRITES=1`.

- [ ] Implement endpoints/client/catalog.

Add endpoint constants:

```python
COMPLIANCE_OVERVIEW = "/api/compliance/overview"
COMPLIANCE_EVENTS = "/api/compliance/events"
COMPLIANCE_EVALUATE = "/api/compliance/evaluate"
```

Add client methods:

```python
async def compliance_overview(self) -> Result: ...
async def compliance_events(self, permit_id=None, start=None, end=None, status=None) -> Result: ...
async def compliance_evaluate(self, permit_id: int, start: str, end: str) -> Result: ...
```

Add catalog capabilities using the existing `_obj` helper.

- [ ] Implement CLI command group.

Commands:

```bash
scada compliance overview --json-output
scada compliance events [--permit-id N] [--start ISO] [--end ISO] [--status TEXT] --json-output
scada compliance evaluate --permit-id N --start ISO --end ISO --json-output
```

Register in `cli.py` with `cli.add_command(compliance_cmd)`.

- [ ] Implement MCP typed functions.

Add:

- `compliance_overview()`
- `compliance_list_events(...)`
- `compliance_evaluate(...)`

Register in `_TOOL_REGISTRY`.

- [ ] Run targeted checks.

Run:

```powershell
just cli-check
just mcp-check
```

Expected: pass.

- [ ] Commit.

```powershell
git add scada-reporter/packages/scada-core scada-reporter/agent-harness mcp-servers/mcp-scada
git commit -m "feat(compliance): add agent read surface"
```

## Task 5: Documentation and Final Verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `scada-reporter/agent-harness/skills/SKILL.md`
- Modify: `README.md`

- [ ] Document CLI commands.

Add commands:

```bash
scada compliance overview --json-output
scada compliance events --json-output
scada compliance evaluate --permit-id 1 --start 2026-05-01T00:00:00 --end 2026-06-01T00:00:00 --json-output
```

- [ ] Run final targeted backend and agent checks.

Run:

```powershell
cd scada-reporter/backend
pytest tests/test_compliance_models.py tests/test_compliance_engine.py tests/test_compliance_api.py -q
cd C:\project\smart
just cli-check
just mcp-check
```

- [ ] Run broader check if targeted checks pass.

Run:

```powershell
just check
```

If too slow or blocked by unrelated existing failures, record the exact failing command and output.

- [ ] Commit.

```powershell
git add AGENTS.md scada-reporter/agent-harness/skills/SKILL.md README.md
git commit -m "docs(compliance): document agent commands"
```

## Final Acceptance Checklist

- [ ] Compliance tables exist in SQLAlchemy metadata and Alembic migration.
- [ ] `ComplianceEvent.event_key` has a database-level unique constraint.
- [ ] Engine creates one deterministic event per permit/parameter/limit/type/period.
- [ ] Re-running evaluation updates existing events instead of duplicating them.
- [ ] Hybrid lab-required parameters do not become compliant from SCADA fallback alone.
- [ ] Bad-quality readings below OPC good quality 192 create `bad_quality` events.
- [ ] First event note resolves related `needs_explanation`.
- [ ] API exposes overview, permit creation, event listing, notes, status transition, and evaluate.
- [ ] Admin/operator/viewer permissions match the Phase 1 scope.
- [ ] CLI prints stable JSON for overview/events/evaluate.
- [ ] MCP read compliance tools are available by default; evaluate is write-gated.
- [ ] Targeted backend, CLI, and MCP tests pass.

## Self-Review

Spec coverage:

- Data model: Task 1.
- Deterministic engine, event key, hybrid handling, bad quality, needs-explanation lifecycle: Task 2.
- API, RBAC, audit, pagination-ready events: Task 3.
- Agent/CLI/MCP read surface and write-gated evaluate: Task 4.
- Documentation and verification: Task 5.

Known gaps by design:

- Report packs, approval, frontend, AI assistant, scheduled period-close generation, and official output rendering are intentionally deferred to later plans.

Placeholder scan:

- No unfinished markers or unspecified implementation steps remain in this plan.

Type consistency:

- Endpoint/capability names use the `compliance_*` prefix consistently.
- Status names match the spec: `open`, `acknowledged`, `resolved`, `waived`.
- Report-pack `failed` clarification remains in the design spec but is not implemented in this Phase 1 plan.
