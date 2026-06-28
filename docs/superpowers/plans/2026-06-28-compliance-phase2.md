# Compliance Phase 2 Implementation Plan — Operations UI + Config API

**Goal:** Make the Compliance Center usable from the web app. Add the permit-configuration CRUD API that Phase 1 deferred, then build the frontend Compliance Center (Overview, Permit Profile config, Events work queue).

**Builds on:** Phase 1 (`docs/superpowers/plans/2026-06-28-compliance-foundation.md`) — models `app/models/compliance.py`, engine `app/services/compliance_engine.py`, API `app/api/compliance.py` (overview/permits-list+create/evaluate/events/notes/status), agent surface. Design spec: `docs/superpowers/specs/2026-06-28-compliance-center-design.md` (API Design + Frontend Design sections are authoritative).

**Scope (Phase 2):**
- Backend: nested config CRUD (discharge points, parameters, limits) + permit detail/update/soft-delete.
- Frontend: `/compliance` route + nav, Overview tab, Permit Profile config tab (admin), Events work queue tab.

**Out of scope (later phases):** Report packs, approval flow, AI assistant, scheduled period-close.

---

## Execution Rules
- TDD: failing test → implement → green.
- Per-task commits. Do not push until all green.
- Backend uses `python` (Windows), match existing router conventions (`require_role`, `require_writable`, `record_audit`, async session).
- Frontend: hand-written typed functions in `src/api/client.ts` (no gen-client needed); TanStack Query; i18n keys added to ALL 5 locales (en/tr/ru/de/ar) — `parity.test.ts` enforces this.
- Admin-only for all config writes; reject hard-delete of permits with events.

---

## Task A: Permit Config CRUD API

**Files:** modify `app/api/compliance.py`; add tests `tests/test_compliance_config_api.py`.

Endpoints (all config writes ADMIN + `require_writable` + audit):
- `GET /permits/{permit_id}` — permit detail with nested points/parameters/limits (auth).
- `PUT /permits/{permit_id}` — update metadata (admin).
- `DELETE /permits/{permit_id}` — soft delete: set `is_active=false`; reject (409) hard delete if events exist.
- `GET /permits/{permit_id}/points`, `POST /permits/{permit_id}/points`, `PUT /points/{point_id}`, `DELETE /points/{point_id}`.
- `GET /permits/{permit_id}/parameters`, `POST /permits/{permit_id}/parameters`, `PUT /parameters/{parameter_id}`, `DELETE /parameters/{parameter_id}`.
- `GET /parameters/{parameter_id}/limits`, `POST /parameters/{parameter_id}/limits`, `PUT /limits/{limit_id}`, `DELETE /limits/{limit_id}`.

Validation:
- `source_type` in SOURCE_TYPES; `scada`→tag_id required, `lab`→lab_parameter_id required, `hybrid`→both.
- New parameter's `discharge_point_id` must belong to the path `permit_id` (else 400/422).
- `limit_type` in LIMIT_TYPES, `aggregation` in AGGREGATIONS, severity sane.
- 404 on missing ids; 403 for operator on config writes.

Audit actions: `compliance.point.{create,update,delete}`, `compliance.parameter.*`, `compliance.limit.*`, `compliance.permit.{update,delete}`.

Tests: admin CRUD happy paths for point/parameter/limit; operator 403; source_type validation; permit soft-delete sets is_active=false; delete permit with events → 409; GET permit detail returns nested graph.

Verify: `python -m pytest tests/test_compliance_config_api.py tests/test_compliance_api.py -q -p no:randomly` green; then full suite no new failures. Commit `feat(compliance): permit config CRUD API`.

---

## Task B: Frontend Compliance Center

**Files:** create `src/pages/compliance/` (ComplianceCenter.tsx + Overview/Permits/Events components + helpers); modify `src/App.tsx` (route), `src/components/Layout.tsx` (nav), `src/api/client.ts` (compliance functions + types), i18n locales (nav + page strings in all 5). Tests under `src/pages/compliance/__tests__/`.

API client (`src/api/client.ts`): typed functions + interfaces for every compliance endpoint (overview, permits list/get/create/update/delete, points/parameters/limits CRUD, events list/get/notes/status, evaluate).

Route: `<Route path="compliance" element={<ComplianceCenter />} />`. Nav: `{ to: '/compliance', labelKey: 'nav_compliance' }` (place near reports/lab). i18n: `nav_compliance` + all page strings in en/tr/ru/de/ar.

UI (tabs in one page):
- **Overview:** counter cards (active permits, open events, open by type, missing samples, events needing explanation), 30-day event trend (recharts), primary actions (run evaluation → calls `/evaluate` with a permit+period picker; open events tab). Any authenticated user.
- **Permit Profiles (admin):** permit list + create; permit detail with sections for metadata, discharge/sample points, parameter source mapping, limit rules; inline create/edit/delete for points/parameters/limits. Compact operational layout (per design). Config controls hidden/disabled for non-admin.
- **Events work queue:** filter bar (period, permit, point, parameter, severity, status); table rows (type, parameter, observed, limit, period, evidence preview, notes count, status action); detail panel (evidence table, source readings, operator notes, status transition controls with mandatory waive reason). Operator+admin can add notes / change status.

Tests: overview counters render from mocked API; events filters work; permission-gated config + approve controls hidden for non-admin (use viewer/operator mock); i18n parity passes.

Verify: `pnpm test` (or `just frontend-check`) green; `pnpm tsc --noEmit` clean; i18n `parity.test.ts` passes. Commit `feat(compliance): Compliance Center frontend`.

---

## Task C: Docs + Final Verification
- Update README feature list + AGENTS/SKILL if new agent-relevant surface (none new — reads already documented).
- Run `just check` (or targeted backend + frontend + cli + mcp). Record any pre-existing unrelated failures (e.g. `test_grafana_render_config` env SA-token).
- Commit `docs(compliance): note Phase 2 operations UI`.

## Acceptance
- Admin can create a permit, add points/parameters/limits, edit and soft-delete — all from the UI.
- Operator can run evaluation, browse the events queue, add notes, change event status (waive requires reason).
- Non-admin cannot see/use config write controls.
- Overview counters + trend render from API.
- i18n parity holds across 5 locales; tsc clean; backend+frontend tests green.
