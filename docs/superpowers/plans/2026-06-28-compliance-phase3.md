# Compliance Phase 3 Implementation Plan — Official Report Packs

**Goal:** Period-level official compliance report packs: model + generation (PDF/Excel/JSON), review→approval flow with evidence freeze, blocking on unresolved required explanations, scheduler period-close draft creation, and a frontend Report Packs tab.

**Builds on:** Phases 1+2 — models `app/models/compliance.py`, engine `app/services/compliance_engine.py`, API `app/api/compliance.py` (overview/permits/config CRUD/events/notes/status/evaluate), frontend `src/pages/compliance/`. Design: `docs/superpowers/specs/2026-06-28-compliance-center-design.md` (Official Report Pack + Evidence Immutability + Report Pack Content + Scheduler Behavior sections are authoritative).

**Out of scope (Phase 4):** AI Compliance Assistant, email distribution, e-signature, portal submission.

## Key design decisions
- **Output storage:** the pack stores its own generated outputs as blobs (`pdf_blob`, `xlsx_blob`, `json_blob` `LargeBinary`, nullable) + `error_message`. The design's `archive_id -> report_archive.id` is kept as a nullable column for future linkage but NOT used in Phase 3 — `report_archive`'s schema (tag_ids/interval/output_format required) does not fit permit/period packs. Note this deviation.
- **Statuses:** `draft` → `ready_for_review` → `approved` → `exported`; `failed` on generation error.
- **Evidence immutability:** on `approve`, freeze `events_snapshot_json` (the covered events + evidence at approval time). Re-evaluating the period afterward never mutates an approved pack. A period that already has an `approved`/`exported` pack is not auto-overwritten; a new pack is a revision.
- **Blocking:** `approve` is rejected (409) while any required `needs_explanation` event for the permit+period is still `open` (no operator note).

---

## Execution Rules
- TDD: failing test → implement → green. Per-task commits, no push until all green.
- `python` on Windows. Match existing conventions (`require_role`, `require_writable`, `record_audit`, async session, scheduler `add_job` cron like `db_backup`).
- Reuse `weasyprint`+jinja2 (`app/templates/`) for PDF and `openpyxl` for Excel; mirror `pdf_builder.py`/`excel_builder.py` style.

---

## Task A: Report Pack Model + Migration
**Files:** add `ComplianceReportPack` to `app/models/compliance.py`; migration in `alembic/versions/`; tests `tests/test_compliance_reportpack_models.py`.

Model `compliance_report_packs`: id, permit_id (FK), period_start, period_end, status (default `draft`), events_snapshot_json (nullable Text), archive_id (FK report_archive.id, nullable), pdf_blob/xlsx_blob/json_blob (LargeBinary nullable), error_message (nullable Text), prepared_by (FK users.id nullable), approved_by (FK users.id nullable), approved_at (nullable), created_at, updated_at. Index on (permit_id, period_start) and status. No cascade-delete (legal record). Add `REPORT_PACK_STATUSES = ("draft","ready_for_review","failed","approved","exported")` constant.

Migration creates the table + indexes; working downgrade drops it. Register import already covered by `app.models.compliance`. Verify migration applies on fresh sqlite. Commit `feat(compliance): report pack model`.

## Task B: Report Pack Generation Service
**Files:** `app/services/compliance_report.py`; jinja2 template `app/templates/compliance_report.html.j2`; tests `tests/test_compliance_report.py`.

`build_report_pack_data(db, permit_id, period_start, period_end) -> dict` — assemble logical sections: cover (permit metadata), period summary, parameter+limit table, measurement results, compliance event summary, missing-sample list, bad-quality list, operator explanations (event notes), approval block, audit metadata.

Functions: `render_json(data) -> bytes`, `render_excel(data) -> bytes` (openpyxl, one sheet per logical section or a sectioned workbook), `render_pdf(data, lang) -> bytes` (weasyprint via the new template). JSON and Excel/PDF contain the same logical sections.

Tests: JSON output includes every expected section key; Excel/PDF generation returns non-empty bytes and includes compliance sections (assert sheet titles / rendered text); a period with breaches lists them.

Commit `feat(compliance): report pack generators`.

## Task C: Report Pack API + Scheduler
**Files:** extend `app/api/compliance.py`; extend `app/services/scheduler.py`; tests `tests/test_compliance_reportpack_api.py`.

Endpoints (prefix `/compliance`):
- `GET /report-packs` (auth) — list with permit_id filter + limit/offset, `{total, items}`.
- `POST /report-packs` (operator+admin) — create draft for permit+period (evaluates first or uses existing events). Audit `compliance.reportpack.create`.
- `GET /report-packs/{id}` (auth) — pack detail (status, blocking issues, has-outputs flags).
- `POST /report-packs/{id}/generate` (operator+admin) — build pdf/xlsx/json blobs; on success keep `draft`; on error set `failed` + error_message. Audit `compliance.reportpack.generate`.
- `POST /report-packs/{id}/submit-review` (operator+admin) — `draft`→`ready_for_review` (requires outputs generated).
- `POST /report-packs/{id}/approve` (ADMIN + require_writable) — reject 409 if any required `needs_explanation` open for permit+period OR outputs missing; else freeze `events_snapshot_json`, set status `approved`, approved_by/at. Audit `compliance.reportpack.approve`.
- `GET /report-packs/{id}/download?format=pdf|excel|json` (auth) — stream the stored blob with correct content-type/filename; if status `approved`, may flip to `exported`. 404 if not generated.
- `DELETE /report-packs/{id}` (admin) — allowed only while `draft` or `failed`; approved/exported immutable → 409.

Scheduler period-close job (`compliance_period_close`, cron daily like `db_backup`): for each active permit whose reporting period just closed, create a `draft` pack if none exists for that period; skip periods that already have an `approved`/`exported` pack; mark a pack `blocked`-equivalent (keep `draft` + populate blocking issues) if unresolved required events remain. Gate behind a settings flag (e.g. `RUN_COMPLIANCE_SCHEDULER`, default true) mirroring backup scheduler.

Tests: create→generate→submit-review→approve happy path; approve blocked (409) when required needs_explanation open; approve freezes snapshot (re-evaluate after approve does not change snapshot); download returns bytes per format; delete approved → 409; operator cannot approve (403); RBAC + audit rows.

Verify targeted + full backend suite (allow only the known pre-existing `test_grafana_render_config` failure). Commit `feat(compliance): report pack API and scheduler`.

## Task D: Frontend Report Packs Tab
**Files:** `src/pages/compliance/ReportPacksTab.tsx` (+ wire into `ComplianceCenter.tsx` tabs); `src/api/client.ts` (report-pack functions/types); i18n `compliance.json` ×5 locales (new keys); tests under `src/pages/compliance/__tests__/`.

Flow (per design): select permit+period → create/list packs → readiness check (show blocking issues) → generate → preview/download PDF/Excel/JSON → submit review → approve (admin only) → download. Approve control hidden for non-admin. Show status badges (draft/ready_for_review/failed/approved/exported).

Tests: pack list renders from mocked API; approve button hidden for non-admin; blocking issues shown when present; i18n parity holds. Verify `pnpm tsc --noEmit` + `pnpm test` (compliance + parity green; known pre-existing Grafana/Dashboard failures allowed). Commit `feat(compliance): report packs frontend`.

## Task E: Docs + Final Verification
- README: extend Compliance Center page row + `/api/compliance` to mention report packs.
- Run targeted backend + frontend + cli + mcp checks; record pre-existing unrelated failures only.
- Commit `docs(compliance): note Phase 3 report packs`.

## Acceptance
- Admin/operator can create + generate a report pack (PDF/Excel/JSON) for a permit+period.
- Approve is blocked while required explanations are missing; approving freezes the evidence snapshot.
- Approved packs are immutable (re-eval doesn't change them; delete rejected).
- Download returns the correct file per format.
- Scheduler creates draft packs at period close, skipping already-approved periods.
- Frontend Report Packs tab drives the full flow; approve hidden for non-admin.
- Backend + frontend compliance tests green; i18n parity holds.
