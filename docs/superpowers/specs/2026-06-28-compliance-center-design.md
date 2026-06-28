# Compliance Center Design

Date: 2026-06-28
Status: Approved for implementation planning
Scope: Water/wastewater permit compliance, official report packs, and agent-facing compliance workflows.

## Context

EKONT SMART REPORT already collects PLC data, stores time-series readings, supports lab data entry, generates advanced reports, embeds Grafana panels, exposes audit logs, and provides an agent-native CLI/MCP contract. The next product step is to make the system stronger than generic SCADA reporting tools by focusing on the highest-value water/wastewater workflow: defensible regulatory and permit compliance reporting.

Comparable products emphasize scheduled reporting, web report portals, KPI/performance dashboards, and water compliance data management:

- Ignition Reporting supports custom and scheduled reports over SQL, realtime tags, and external API data.
- Dream Report emphasizes automated scheduled industrial reporting and a web portal for report access and on-demand generation.
- Siemens Performance Insight emphasizes standard/custom KPI calculation and rapid dashboard/report creation.
- Hach WIMS emphasizes water/wastewater data centralization, audit trails, and compliance reporting across process, lab, field, and other sources.

The selected direction is option A: municipality and water/wastewater facility compliance plus official reporting.

## Goals

- Add a permit-driven compliance layer above existing SCADA, lab, report, audit, scheduler, CLI, and MCP surfaces.
- Detect limit breaches, missing samples, late samples, bad-quality readings, and items that need operator explanation.
- Generate official report packs for a reporting period with evidence, explanations, approval state, and archived outputs.
- Keep the model configurable instead of hard-coding one jurisdiction's report format.
- Make compliance status queryable from the UI, CLI, and MCP/agent contract.

## Non-Goals

- No direct government portal submission in the first release.
- No real electronic signature integration in the first release.
- No separate mobile app in the first release.
- No replacement of the existing Lab Data Entry, Advanced Reports, Grafana, or audit screens.
- No AI-only compliance decisions; the compliance engine must remain deterministic and auditable.

## Product Positioning

Compliance Center should make the product feel like a water/wastewater compliance operations system, not just a dashboard exporter. The differentiator is that the system knows the facility permit requirements, continuously compares actual SCADA/lab data against those requirements, and packages the result into reviewable, auditable reports.

The core promise:

> Operators and environmental engineers can see whether the period is report-ready, why it is not ready, what evidence supports each issue, and who approved the final pack.

## Architecture

Compliance Center adds five bounded areas.

### Permit Profile

Stores the configured compliance obligations for a facility or discharge permit:

- facility and authority metadata
- permit number and validity range
- discharge/sample points
- monitored parameters
- source mapping to SCADA tags or lab parameters
- limit rules and sample-frequency rules
- reporting frequency

### Compliance Engine

Reads existing SCADA and lab data and evaluates permit rules over a time window. The engine is deterministic and creates durable compliance events rather than transient UI-only warnings.

The main service interface is:

```python
ComplianceEngine.evaluate_permit(permit_id, period_start, period_end)
```

The engine must support:

- instantaneous min/max checks
- daily average checks
- monthly average checks
- minimum sample count checks
- sample frequency checks
- bad PLC quality checks
- repeated event upsert to avoid duplicate rows on re-evaluation

#### Time Zone Semantics

Compliance periods are calendar-based (a daily average, a "May" monthly report), so day and month boundaries must be computed in the facility's local time, not raw UTC. Rules:

- Readings are stored as naive UTC (consistent with the existing poller normalization). The engine resolves the facility time zone from the application IANA time-zone setting and converts window boundaries before aggregating.
- `daily_avg` buckets run from local midnight to local midnight; `monthly_avg` buckets run from the first to the last local day of the month. The engine converts these local boundaries to UTC for the actual `tag_readings`/lab queries.
- `period_start` and `period_end` on permits, events, and report packs are stored as naive UTC instants marking the resolved boundaries, but are derived from local calendar units so a "May report pack" covers May in facility-local time.
- Scheduled and manual runs use the same time zone resolution, so a manual re-run of a period produces identical bucket boundaries (supports the deterministic/idempotent requirement).

### Compliance Events

Compliance events record the output of the engine. They are the main operational queue for operators and environmental staff.

Event types:

- `limit_exceeded`
- `missing_sample`
- `late_sample`
- `bad_quality`
- `needs_explanation`

Event-type generation mapping (which engine check produces which type):

- `limit_exceeded` — instant min/max, daily-average, and monthly-average checks when an aggregated value violates a `value_limit`.
- `missing_sample` — `sample_count` checks when fewer samples exist in the period than the rule requires (including the zero-data case from Error Handling).
- `late_sample` — `sample_frequency` checks when the gap between consecutive samples exceeds the configured `sample_frequency` interval (a sample arrived, but later than the required cadence).
- `bad_quality` — `quality` checks when source PLC readings carry a non-good OPC quality (see threshold below).
- `needs_explanation` — not produced directly by a numeric rule. It is raised for any `open` `limit_exceeded`/`missing_sample`/`late_sample`/`bad_quality` event on a parameter/limit flagged as explanation-required (a `requires_explanation` flag on `compliance_limits`) that has no `compliance_event_notes` entry. It blocks report-pack approval until an operator note is added. The engine derives it from existing events rather than from raw readings.

`needs_explanation` lifecycle: adding the first note to the source event automatically resolves the related `needs_explanation` event in the same transaction. A later engine re-run may re-open or create a new `needs_explanation` event only if the source event remains open and has no notes after the re-evaluation.

Bad-quality threshold: a reading is bad-quality when `tag_readings.quality < 192` (OPC `Good` = 192). The `quality` limit type may override the threshold per parameter, but 192 is the default cutoff.

Event statuses:

- `open`
- `acknowledged`
- `resolved`
- `waived`

Status transitions stamp who/when: `acknowledged` sets `acknowledged_by`/`acknowledged_at`, `resolved` sets `resolved_by`/`resolved_at`, `waived` sets `waived_by`/`waived_at` and requires a non-empty `waive_reason` (waiving a breach is legally sensitive — the reason is mandatory and audited). Every transition also writes an audit row.

Each event stores evidence JSON with the values, timestamps, limit rule, source records, and aggregation details that produced the event.

### Official Report Pack

A report pack is the period-level compliance artifact. It combines generated report files with deterministic compliance status and human review state.

Report pack statuses:

- `draft`
- `ready_for_review`
- `failed`
- `approved`
- `exported`

Outputs:

- JSON for agent/API use
- Excel for operational review
- PDF for official sharing and audit archive

#### Evidence Immutability

An approved or exported report pack is a legal record and must not silently change when the underlying period is re-evaluated. Rules:

- On `approve`, the pack captures an immutable snapshot of the compliance events and evidence it covers (an `events_snapshot_json`, or a row-level freeze that copies the relevant `compliance_events` evidence into the pack). The generated PDF/Excel/JSON archive is the canonical frozen artifact.
- After a pack reaches `approved` or `exported`, re-evaluating the same permit and period is still allowed (events keep updating live), but it does not mutate the approved pack. Any post-approval divergence between live events and the frozen snapshot is surfaced as a new event/flag, not an in-place edit of the approved pack.
- A period that already has an `approved` pack is reported as such; producing a new official artifact for that period requires creating a new pack (revision), leaving the original approved pack and its archive intact for audit.

### Agent Surface

The agent surface exposes compliance commands in the same style as the existing SCADA agent contract.

Initial CLI commands:

```bash
scada compliance overview --json-output
scada compliance permits list --json-output
scada compliance events --permit-id <id> --start <iso> --end <iso> --json-output
scada compliance evaluate --permit-id <id> --start <iso> --end <iso> --json-output
scada compliance report-packs create --permit-id <id> --start <iso> --end <iso> --json-output
scada compliance report-packs approve <id> --json-output
```

Initial MCP capabilities:

- `compliance_overview` (read)
- `compliance_list_events` (read)
- `compliance_evaluate` (write)
- `compliance_create_report_pack` (write)
- `compliance_approve_report_pack` (write)

MCP write capabilities remain gated by the existing `SCADA_MCP_ALLOW_WRITES=1` safety flag.

## Data Model

### `compliance_permits`

Permit profile.

Fields:

- `id`
- `name`
- `facility_name`
- `authority`
- `permit_number`
- `valid_from`
- `valid_to`
- `report_frequency`
- `report_cron`
- `is_active`
- `created_at`
- `updated_at`

Allowed `report_frequency` values:

- `daily`
- `weekly`
- `monthly`
- `quarterly`
- `custom_cron`

`report_cron` is nullable and only valid when `report_frequency = custom_cron`. The first implementation phase may reject `custom_cron` at API validation time if scheduler support is not implemented yet.

### `compliance_discharge_points`

Permit discharge or sample point.

Fields:

- `id`
- `permit_id`
- `code`
- `name`
- `description`
- `lab_sample_point_id`
- `created_at`
- `updated_at`

Foreign keys:

- `permit_id -> compliance_permits.id`
- `lab_sample_point_id -> lab_sample_points.id`, nullable

### `compliance_parameters`

Parameter monitored under a permit.

Fields:

- `id`
- `permit_id`
- `discharge_point_id`
- `parameter_name`
- `unit`
- `source_type`
- `tag_id`
- `lab_parameter_id`
- `created_at`
- `updated_at`

Constraints:

- `source_type` is one of `scada`, `lab`, `hybrid`.
- At least one of `tag_id` or `lab_parameter_id` is required.
- `scada` requires `tag_id`; `lab` requires `lab_parameter_id`; `hybrid` requires both.

Hybrid source resolution: for a `hybrid` parameter the lab measurement is authoritative for the compliance value (regulatory limits are defined against lab methods), and the SCADA tag provides continuous context plus `bad_quality`/`missing_sample` detection between lab samples. When both a lab value and a SCADA aggregate exist for the same window, the engine evaluates the `value_limit` against the lab value and records the SCADA aggregate in `evidence_json` for cross-reference. If the required lab value is absent for a window, the engine keeps a `missing_sample` event open and must not mark the parameter compliant from SCADA data alone. The SCADA aggregate may appear only as provisional/context evidence in `evidence_json`.

Note: `permit_id` here is denormalized (reachable via `discharge_point_id -> compliance_discharge_points.permit_id`). It is kept for query convenience but must be validated to match the discharge point's permit at write time to avoid divergence.

Foreign keys:

- `permit_id -> compliance_permits.id`
- `discharge_point_id -> compliance_discharge_points.id`
- `tag_id -> tags.id`, nullable
- `lab_parameter_id -> lab_parameters.id`, nullable

### `compliance_limits`

Limit or sampling rule for a compliance parameter.

Fields:

- `id`
- `compliance_parameter_id`
- `limit_type`
- `min_value`
- `max_value`
- `aggregation`
- `window`
- `sample_frequency`
- `severity`
- `requires_explanation`
- `created_at`
- `updated_at`

`requires_explanation` (bool, default false): when true, an `open` event from this limit also raises a `needs_explanation` event until an operator note exists, and blocks report-pack approval.

`window` qualifies the `aggregation` bucket when the aggregation alone is ambiguous (e.g. a rolling window distinct from the calendar `daily_avg`/`monthly_avg` buckets). For the standard calendar aggregations it is redundant and may be left null; the engine prefers `aggregation` and only consults `window` for rolling/custom windows.

Allowed `limit_type` values:

- `value_limit`
- `sample_count`
- `sample_frequency`
- `quality`

Allowed `aggregation` values:

- `instant`
- `daily_avg`
- `monthly_avg`
- `count`

### `compliance_events`

Durable compliance findings created by the engine.

Fields:

- `id`
- `permit_id`
- `parameter_id`
- `limit_id`
- `event_type`
- `severity`
- `period_start`
- `period_end`
- `observed_value`
- `limit_value`
- `status`
- `event_key`
- `evidence_json`
- `created_at`
- `updated_at`
- `acknowledged_at`
- `acknowledged_by`
- `resolved_at`
- `resolved_by`
- `waived_at`
- `waived_by`
- `waive_reason`

Uniqueness:

- `event_key` is a deterministic hash of `(permit_id, parameter_id, limit_id, event_type, period_start, period_end)`, stored on the row and backed by a `UNIQUE` constraint/index. The engine upserts on `event_key`, so re-evaluating the same permit and period updates the existing row instead of inserting a duplicate. This column makes the "repeated event upsert" requirement in the Compliance Engine section enforceable at the database level rather than only in application code.

### `compliance_event_notes`

Human explanations and corrective-action notes.

Fields:

- `id`
- `event_id`
- `user_id`
- `note`
- `created_at`

Foreign keys:

- `event_id -> compliance_events.id`
- `user_id -> users.id`

Notes are append-only (no `updated_at`); corrections are added as new notes so the explanation history stays auditable.

### `compliance_report_packs`

Period-level official report package.

Fields:

- `id`
- `permit_id`
- `period_start`
- `period_end`
- `status`
- `archive_id`
- `events_snapshot_json`
- `prepared_by`
- `approved_by`
- `approved_at`
- `created_at`
- `updated_at`

`events_snapshot_json` is null until approval; on `approve` it is frozen with the covered events and their evidence (see Evidence Immutability under Official Report Pack).

Foreign keys:

- `archive_id -> report_archive.id`, nullable until output generation completes. (Table name is singular `report_archive`, matching `app/models/report_archive.py`.)

## API Design

Prefix: `/api/compliance`

Permit profile endpoints:

- `GET /permits`
- `POST /permits`
- `GET /permits/{permit_id}`
- `PUT /permits/{permit_id}`
- `DELETE /permits/{permit_id}` — soft delete. A permit is a legal record with attached events and report packs; `DELETE` sets `is_active = false` (deactivate) rather than removing rows. Hard delete is rejected when the permit has any compliance events or report packs, to avoid orphaning audit history.

Discharge point endpoints:

- `GET /permits/{permit_id}/points`
- `POST /permits/{permit_id}/points`
- `PUT /points/{point_id}`
- `DELETE /points/{point_id}`

Parameter and limit endpoints:

- `GET /permits/{permit_id}/parameters`
- `POST /permits/{permit_id}/parameters`
- `PUT /parameters/{parameter_id}`
- `DELETE /parameters/{parameter_id}`
- `GET /parameters/{parameter_id}/limits`
- `POST /parameters/{parameter_id}/limits`
- `PUT /limits/{limit_id}`
- `DELETE /limits/{limit_id}`

Evaluation endpoints:

- `POST /evaluate`
- `GET /overview`
- `GET /events`
- `GET /events/{event_id}`
- `POST /events/{event_id}/notes`
- `PATCH /events/{event_id}/status`

Report pack endpoints:

- `GET /report-packs`
- `POST /report-packs`
- `GET /report-packs/{pack_id}`
- `DELETE /report-packs/{pack_id}` — allowed only while status is `draft` or `failed`; approved/exported packs are immutable and cannot be deleted.
- `POST /report-packs/{pack_id}/generate`
- `POST /report-packs/{pack_id}/submit-review`
- `POST /report-packs/{pack_id}/approve`
- `GET /report-packs/{pack_id}/download`

Pagination: list endpoints that can grow unbounded (`GET /events`, `GET /report-packs`) accept `limit` and `offset` (or cursor) query params and return a total count, so the events work queue and pack history stay bounded per request.

## Frontend Design

New route: `/compliance`

Sidebar label: `Compliance Center`

### Overview

Purpose: show period readiness at a glance.

Widgets:

- active permits
- open events
- missing samples
- unresolved explanations
- report packs waiting for approval
- risk by parameter
- 30-day event trend

Primary actions:

- run evaluation
- create report pack
- open event queue

### Permit Profiles

Purpose: admin configuration.

Sections:

- permit metadata
- discharge/sample points
- parameter source mapping
- limit rules
- report frequency
- active/inactive status

This screen should use a compact, operational layout rather than a marketing-style wizard. The operator needs fast scanning and reliable edits.

### Compliance Events

Purpose: daily work queue.

Filters:

- period
- permit
- discharge point
- parameter
- severity
- status

Row details:

- event type
- parameter
- observed value
- limit
- period
- evidence preview
- notes count
- status action

Detail panel:

- evidence table
- source readings
- operator notes
- audit-style history
- status transition controls

### Report Packs

Purpose: official review and export.

Flow:

1. select permit and period
2. run readiness check
3. show blocking issues
4. generate PDF/Excel/JSON preview
5. send to review
6. approve
7. archive/export

The first release requires approval inside the app but does not integrate external digital signature providers.

### AI Compliance Assistant

Placement: right-side panel or separate tab inside Compliance Center.

Supported prompts:

- "Is this month ready for reporting?"
- "Which permit limits were exceeded?"
- "What explanations are still missing?"
- "Draft an operator explanation for this event."
- "Create the May report pack."

AI outputs must link back to deterministic event IDs and report pack IDs. The assistant cannot approve report packs without explicit user action and permission.

## Report Pack Content

PDF and Excel outputs contain:

- cover page with permit metadata
- reporting period summary
- parameter and limit table
- measurement results
- compliance event summary
- missing sample list
- bad-quality reading list
- operator explanations
- approval block
- audit metadata

JSON output contains the same logical sections in machine-readable form.

## Scheduler Behavior

Daily job:

- evaluate active permits for the current reporting period
- create or update compliance events

Period-close job:

- create draft report packs for permits whose reporting period closed
- mark packs as blocked if unresolved required events remain
- skip periods that already have an `approved` or `exported` pack (do not overwrite a frozen pack; a revision is created explicitly, see Evidence Immutability)

Manual runs:

- can be triggered from UI, CLI, or MCP write capabilities
- must produce the same event results as scheduled runs for the same period

## Permissions

Initial permission model:

- Admin: manage permits, limits, report pack approval, all event status transitions.
- Operator: view overview/events, add notes, acknowledge events, run evaluation.
- Viewer: view overview, events, and approved report packs.

Report approval requires admin role or a future explicit permission such as `compliance_report:approve`.

All create/update/delete/approve actions write audit rows.

## Error Handling

- Evaluation with no matching data creates missing-data events instead of failing the whole run.
- Invalid permit configuration returns clear validation errors before evaluation.
- Source mapping conflicts are rejected at API validation time.
- Report pack generation fails with a persistent failed status and error message.
- Re-running evaluation is idempotent for the same permit and period.

## Testing Strategy

Backend unit tests:

- instant min/max limit evaluation
- daily and monthly average evaluation
- sample count and frequency evaluation
- bad-quality PLC reading detection
- deterministic event upsert behavior

Backend API tests:

- permit CRUD
- discharge point CRUD
- parameter and limit CRUD
- event list filters
- event note and status transitions
- report pack create, generate, review, approve
- RBAC and audit behavior

Report tests:

- JSON report pack includes expected sections
- PDF/Excel generation includes compliance sections
- report pack blocks approval when required explanations are missing

Frontend tests:

- overview counters render from API data
- event filters work
- permission-gated approve controls are hidden for non-admin users
- report pack status flow renders correctly

CLI/MCP tests:

- compliance commands emit stable JSON
- read capabilities are exposed by default
- write capabilities obey existing MCP write gating

Migration tests:

- all compliance tables are created
- foreign keys and check constraints exist
- downgrade removes compliance tables safely where the repository migration policy requires downgrade support

## Phasing

### Phase 1: Compliance Foundation

- migrations and models
- permit CRUD
- parameter/limit CRUD
- deterministic engine for limit, missing sample, and quality events
- events API
- backend tests

### Phase 2: Operations UI and Agent Reads

- Compliance Center route
- overview
- permit profile screen
- events work queue
- CLI read commands
- MCP read capabilities

### Phase 3: Report Packs

- report pack model and API
- PDF/Excel/JSON compliance sections
- review and approval flow
- archive integration
- scheduler period-close draft generation

### Phase 4: AI and Write Automation

- AI Compliance Assistant
- CLI write commands
- MCP write capabilities with existing env-gated safety
- explanation drafting linked to event IDs

### Later Phases

- email distribution
- portal submission adapters
- real electronic signature integration
- mobile-first field collection
- jurisdiction-specific templates

## Acceptance Criteria

- Admin can configure a permit, discharge point, parameter source, and limit rules.
- Operator can run evaluation for a selected period and see compliance events.
- Missing sample, limit exceeded, and bad-quality scenarios are detected with evidence JSON.
- Operator can add explanatory notes to an event.
- Admin can create, generate, review, approve, and download a report pack.
- Approved report packs are linked to report archives.
- CLI can return compliance overview and event data as JSON.
- MCP exposes compliance read capabilities by default and write capabilities only when write gating is enabled.
- Tests cover engine behavior, API permissions, report pack flow, and CLI JSON contract.

## References

- Ignition Reporting documentation: https://www.docs.inductiveautomation.com/docs/8.1/ignition-modules/reporting
- Dream Report product overview: https://dreamreport.net/
- Dream Report Web Portal: https://dreamreport.net/dream-report-web-portal/
- Siemens Performance Insight: https://www.siemens.com/en-us/products/simatic-apps/performance-insight/
- Hach WIMS platform: https://www.hach.com/digital-solutions/wims
- Hach/Aquatic Informatics WIMS overview: https://aquaticinformatics.com/products/hach-wims-water-information-management-solution-platform/
