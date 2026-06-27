# Lab Data Entry & Tracking — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan

## Problem

The system ingests SCADA/PLC time-series automatically, but there is no way to
enter data **manually** from outside the plant. Laboratory analysis and
measurement results (pH, COD, TSS, turbidity, etc.) are produced by lab staff
and must be:

1. Entered through a dedicated UI screen.
2. Tracked on Grafana dashboards alongside the existing SCADA data.
3. Turned into reports via the existing reporting engine.

## Requirements (from brainstorming)

- **Mixed record shape:** some entries are a single numeric measurement; others
  are a sample event with multiple parameters measured at the same time/place,
  plus metadata (sample point, operator, method, batch). One unified model must
  cover both.
- **Grafana bridge — both:** lab data lives primarily in its own tables, exposed
  to Grafana through a time-series SQL view; selected parameters are *also*
  mirrored into `tag_readings` so they can be compared on the same panel as
  SCADA tags and reused by the existing report engine.
- **Entry screen — all four modes:** single-sample form, batch/table grid,
  Excel/CSV import, and edit/delete of existing records (audited).
- **Reports — reuse `advanced_reports`:** mirrored lab parameters are selected
  like tags; statistics + PDF/Excel + embedded Grafana panels all work with no
  new generator code.
- **Catalog — hybrid:** an admin-managed catalog of parameters and sample points
  is the primary list, but operators may add new entries on the fly which land
  as `approved=false` and await admin approval/normalization.
- **Edit/delete permission:** admin, **or** the operator who entered the record
  (`entered_by == current_user`).

## Architecture

### Data model (4 new tables)

```
lab_parameter        lab_sample_point
   id                   id
   code (unique)        code (unique)
   name                 name
   unit                 description
   category             is_active
   min_limit (nullable) approved (bool)
   max_limit (nullable)
   is_active
   approved (bool)            lab_sample
   mirror_to_tag_id ──┐          id
     (nullable FK→tags)│          sample_point_id  FK→lab_sample_point
                       │          sampled_at (datetime, the event time)
                       │          entered_by       FK→users
                       │          method (str)
                       │          batch_no (str)
                       │          note (text)
                       │          created_at
                       │
                       │       lab_measurement
                       │          id
                       └──────    parameter_id  FK→lab_parameter
                                  sample_id     FK→lab_sample (cascade delete)
                                  value (Float, nullable)
                                  text_value (str, nullable — categorical results)
                                  flag (str, nullable — computed, e.g. "over_limit")
```

**Mixed-shape resolution:** a single measurement is just a `lab_sample` with one
`lab_measurement`. A multi-parameter sample is one `lab_sample` with N
`lab_measurement` rows. The same structure covers both — no special case.

**Hybrid catalog:** `approved=false` marks an operator-added parameter/point
awaiting admin review. The entry form selects from the approved catalog and
offers "+ new", which creates an `approved=false` record.

**Indexes:** `lab_measurement(parameter_id)`, `lab_sample(sampled_at)`,
`lab_sample(sample_point_id)`.

### Grafana bridge (both: view + optional mirror)

- **Primary — SQL view `v_lab_timeseries`:**
  `(time, point_code, param_code, param_name, unit, value, min_limit, max_limit)`
  joining `lab_measurement ⋈ lab_sample ⋈ lab_parameter ⋈ lab_sample_point`.
  Lab dashboards query this through the TimescaleDB datasource. Created in the
  Alembic migration; guarded by the existing `_is_timescale` pattern so SQLite
  dev does not break (view skipped or a trivial equivalent).
- **Optional mirror:** when `lab_parameter.mirror_to_tag_id` is set, saving a
  sample also writes `(tag_id, value, timestamp=sampled_at)` into `tag_readings`
  within the same transaction. Mirrored parameters then appear on existing SCADA
  panels and are selectable by `advanced_reports` exactly like a tag.

### Backend — `app/api/lab.py` (prefix `/api/lab`)

**Catalog**
- `GET/POST/PATCH/DELETE /lab/parameters` (filters: approved, active)
- `GET/POST/PATCH/DELETE /lab/sample-points`
- Operator `POST` ⇒ `approved=false`; admin `PATCH approved=true`.

**Samples / measurements**
- `POST /lab/samples` — single or multi:
  `{sample_point_id, sampled_at, method, batch_no, note,
    measurements:[{parameter_id, value|text_value}]}`.
  One transaction; mirrors where configured; computes `flag` from min/max limit.
- `POST /lab/samples/batch` — table entry:
  `{rows:[{sampled_at, sample_point_id, measurements:[...]}]}`.
- `GET /lab/samples` — list/filter (point, parameter, date range, operator) +
  pagination.
- `GET /lab/samples/{id}`
- `PATCH /lab/samples/{id}`, `DELETE /lab/samples/{id}` — audited; allowed for
  admin **or** `entered_by == current_user`.

**Excel/CSV import**
- `POST /lab/import/preview` — upload → column→parameter mapping suggestion +
  row preview (no writes).
- `POST /lab/import/commit` — approved mapping → bulk import, returns
  `{inserted, errors:[...]}` (per-row error tolerance).

**Permissions (existing RBAC)**
- Entry (samples POST/batch/import): `operator` + `admin`.
- Edit/delete: `admin` **or** record owner (`entered_by`).
- Catalog approve/delete: `admin`.
- License: no new feature gate; demo read-only already blocks POSTs.

**Audit:** edit/delete write to the existing `audit_log` (`AuditLog` + `/api/audit`).

### Frontend — `src/pages/LabEntry.tsx`

Sidebar item "Lab Data Entry" (new i18n namespace `lab`, 5 languages). Tabbed
layout following the Dashboard/AdvancedReports pattern:

1. **Single Sample** — sample point combobox ("+ new") + datetime (default now)
   + method/batch/note → value fields for the catalog/point parameters (combobox
   "+ new parameter") → Save. Out-of-range value flagged red immediately from
   catalog min/max.
2. **Batch Table** — grid (row = sample time, column = parameter). Choose
   parameter columns; quick cell entry; add/remove rows; single "Save All" →
   `/lab/samples/batch`.
3. **Import** — upload Excel/CSV → column-mapping UI (excel_templates pattern) →
   preview → "Import". Result summary (inserted / errors).
4. **Records** — filtered list (point/parameter/date/operator) + pagination; row
   `[edit]`/`[delete]` shown only to authorized users (admin or own record);
   edit = single-form modal.

**Catalog management:** a "Lab Catalog" card on the Settings page (admin) —
parameter/point CRUD + pending approvals (`approved=false` badge listing
operator-added entries).

**API client:** regenerate TS types from OpenAPI via `just gen-client`.

### Grafana dashboards

- Provisioned dashboard `scada-reporter/docker/grafana/dashboards/lab-quality.json`
  — point/parameter template variables, time-series panel with min/max threshold
  lines, latest-values table. `configure-grafana-windows-service.ps1` already
  copies dashboards into the service provisioning folder.
- Mirrored parameters additionally appear in existing SCADA dashboards as tags
  (no extra work).

### Reports

- Mirrored lab parameters live in `tag_readings`, so `advanced_reports` selects
  them like a tag → statistics / PDF / Excel / embedded Grafana panels all work.
  **No new generator code.**
- Non-mirrored parameters: a report template can use `v_lab_timeseries` as a SQL
  source via the existing read-only `query` API (`run_sql_query`). Optional;
  the first phase relies on mirroring.

## Testing (TDD; existing pattern — pytest async + xdist + randomly)

- **Model/CRUD:** hybrid catalog (approved flow); sample + measurements in one
  transaction; `flag` computation from min/max.
- **Mirror:** `mirror_to_tag_id` set ⇒ a `tag_readings` row is written; unset ⇒
  not written.
- **Permission:** operator edits/deletes own record; 403 on another's; admin all.
- **Import:** preview mapping + commit with per-row error tolerance.
- **Batch insert.**
- **View query** (when TimescaleDB present).
- **Frontend (vitest):** form validation (out-of-range warning), tab rendering.

## Migration

Single Alembic migration: 4 tables + `v_lab_timeseries` view + indexes. The
single-head chain is preserved.

## Out of scope (YAGNI)

- Sample approval workflow (lab → QA sign-off).
- Dedicated regulatory report template (Phase 2).
- Lab instrument / LIMS integration.
