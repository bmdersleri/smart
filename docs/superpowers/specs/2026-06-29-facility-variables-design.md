# Facility Variables Design

Date: 2026-06-29

## Goal

Define user-managed facility variables for reports so that report values are computed in the backend, not in Excel formulas. The system must support both scalar values and time series, and both advanced reports and Excel templates must consume the same variable catalog.

## Context

The current repository already has two report-oriented systems:

- `advanced_reports` computes per-tag statistics at report generation time.
- `excel_templates` maps worksheet columns to `tag_id + agg` and fills daily values into uploaded templates.

The existing workbook at `xlsx/gunluk_rapor.xlsx` shows that report logic is broader than single-tag aggregation:

- some cells are direct daily measurements
- some cells are sums of multiple tags
- some cells are derived from other calculated values
- some cells currently rely on Excel formulas

That workbook structure makes `tag_id + agg` insufficient as the long-term report model.

## Decisions

### Source of truth

All report calculations will move to the backend. Excel becomes a presentation layer only.

### Variable scope

Facility variables will be defined in a facility-wide shared catalog, not inside a single report template.

This avoids duplicated logic across templates and allows the same variable to be reused by:

- Excel template filling
- advanced reports
- future CLI and API consumers

### Output shapes

The system must support both:

- `scalar` variables: a single computed value for a requested window
- `series` variables: a time series for a requested grain and range

### User management

Variables must be user-managed through the application UI and API. They are not backend-only seeds or hardcoded config.

### Excel binding behavior

When a report binding targets a `series` variable, the user chooses a binding mode:

- `series`: write row-by-row values into the template
- `reduce`: collapse the series to a single scalar before writing

## Variable Model

Facility variables become first-class domain entities.

### `facility_variables`

Core fields:

- `id`
- `code`
- `name`
- `description`
- `kind` (`scalar|series`)
- `value_type` (`number` in v1)
- `unit`
- `expression_json`
- `null_policy` (`skip|zero_fill|fail`)
- `quality_policy` (`good_only|allow_bad`)
- `default_time_grain` (`hour|day|week|month|null`)
- `is_active`
- `version`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

**`version` is not decorative — it carries the recompute-drift contract.** A variable's formula can change after reports have already used it. Generated report files are frozen archives (good), but a **re-run** of the same template recomputes with the current formula and can produce different numbers. To make that auditable:

- `version` is bumped on every change to `expression_json` / policies (not on cosmetic `name`/`description` edits)
- when a report or Excel fill resolves a variable, it records the resolved `(variable_id, version)` in the artifact metadata path defined under "Archive and workbook metadata"
- this does not freeze values (no materialized snapshots in v1 — see Deferred features); it only makes "which formula produced this archive" answerable

### `facility_variable_dependencies`

Normalized dependency tracking:

- `variable_id`
- `depends_on_type` (`tag|variable`)
- `depends_on_tag_id`
- `depends_on_variable_id`

This table exists so the system does not need to re-parse every expression for every dependency lookup, cycle check, or impact view.

### Excel binding extension

Existing `excel_template_columns` remains in place but is extended with:

- `source_type` (`tag|variable`)
- `variable_id`
- `write_mode` (`series|reduce|null`)
- `reduce_op` (`sum|avg|min|max|last|null`)
- `target_mode` (`column|cell`, default `column`)
- `target_cell` (A1-style cell reference, nullable)
- `variable_code_snapshot` (optional display/audit label, nullable)

The column **already has** `tag_id`, `agg`, and a `source_code` field (`String(64)`). `source_code` today holds the WinCC tag code label used by `template_inspector` to validate that a column maps to the expected cell — it is **not** an engine input. The new fields are purely additive; reconcile the existing field as follows:

- `source_type=tag` → unchanged: `tag_id` + `agg`; `source_code` keeps its current validation/label role
- `source_type=variable` → `tag_id` is `NULL`, `agg` is ignored by the engine; `source_code` still means "the workbook header/code cell expected for drift detection" and must not be overloaded with the variable code unless the workbook cell actually contains that code
- `variable_code_snapshot` (or the joined `facility_variables.code`) is used for UI/display/audit; `variable_id` remains the FK the engine resolves
- exactly one of `tag_id` / `variable_id` is non-null (DB-level or validation-level check)

Backward compatibility rule:

- if `source_type=tag`, existing `tag_id + agg` behavior continues
- if `source_type=variable`, the variable engine is used

Targeting rule:

- `target_mode=column` writes row-by-row through the existing `day_to_row` fill loop
- `target_mode=cell` writes one scalar value into `target_cell`
- `write_mode=series` is valid only with `target_mode=column`
- scalar variables and `write_mode=reduce` bindings use `target_mode=cell` in v1; repeating one scalar down a daily column is not a v1 behavior

**Dangling-binding guard.** A column can point at a variable that is later deactivated (`is_active=false`) or whose deps break. A naive fill would then write **blank cells silently** — the same trap as the compliance permit soft-delete. Required behavior:

- deactivating a variable that is referenced by any enabled column is **blocked** (or forces an explicit confirm), surfacing the referencing templates — symmetric to the dependency/impact view
- at fill time, a binding that resolves to an inactive/broken variable raises a visible warning in the fill result, not a silent empty column

## Expression Model

The system uses a constrained JSON expression tree instead of free-text formulas.

This choice is intentional:

- easier validation
- safer persistence
- simpler UI builder
- lower support burden than a general DSL

### Supported operations in v1

- `agg`
- `add`
- `sub`
- `mul`
- `div`
- `const`
- `round`
- `abs`
- `coalesce`
- `series`
- `moving_avg`
- `reduce`
- `ref`

### Scalar / shape helpers

- `const` — a numeric literal: `{ "op": "const", "value": 3.14 }`. Required in v1; fixed multipliers and unit conversions (e.g. `(tag * 3.6)`, `+ offset`) are everywhere in plant reports and there is no other way to inject a constant. Constants are dimensionless unless a future unit-aware extension explicitly adds `unit`.
- `round` — `{ "op": "round", "source": {…}, "ndigits": 2, "mode": "excel" }`. Report cells round; doing it in the engine keeps Excel a pure presentation layer. `mode="excel"` is the v1 default and must match Excel `ROUND` half-away-from-zero behavior. Do not use bare Python `round()` for persisted report values because it uses bankers rounding.
- `abs` — absolute value (e.g. net flow magnitude). `pow`/`sqrt` are **deferred** — not needed by the current workbook.
- `coalesce` — `{ "op": "coalesce", "args": [a, b, …] }` returns the first non-null argument. See operand-null semantics below.

### Operand-null semantics

`null_policy` is a **variable-level** policy (what the final result does about missing buckets). It does **not** define what happens mid-expression when one operand of an `add`/`sub`/`mul`/`div` is null. That must be explicit, or the same formula yields different numbers depending on data gaps:

- v1 rule: arithmetic ops are **SQL-like** — if any operand is null, the result is null (null propagates up the tree)
- to override locally, wrap an operand in `coalesce` (e.g. `add(a, coalesce(b, const 0))` to treat a missing `b` as zero)
- the variable-level `null_policy` then applies once, to the final scalar/series, after the tree has evaluated

This keeps "ignore the gap" an explicit, visible choice in the expression rather than a hidden engine default.

### Shape algebra and alignment

Every expression node resolves to either `scalar` or `series`. V1 must keep the shape rules small and deterministic:

- scalar + scalar arithmetic returns scalar
- series + series arithmetic aligns by bucket key (`day_no` for Excel-month evaluation, timestamp for API preview); a missing bucket on either side is null, then arithmetic null propagation applies
- series + scalar arithmetic broadcasts the scalar across the series buckets
- `coalesce` follows the same shape rules: a scalar fallback such as `{ "op": "const", "value": 0 }` can fill missing buckets in a series expression, while two series args are aligned by bucket key
- `moving_avg` accepts only a series source and returns a series
- `reduce` accepts only a series source and returns a scalar
- validation rejects ambiguous shape combinations instead of guessing

These rules are required before implementation; otherwise Excel fill, preview, and advanced reports can each make different alignment choices for the same expression.

### Aggregation functions

Both `agg` and `series` ops take an `agg` field. The supported set **must match the existing roll-up engine** (`app/services/template_fill/daily_rollup.py`, `AGGS = {sum, avg, min, max, last, delta}`) so the variable engine and the current Excel fill can produce identical numbers when evaluated with the same quality policy:

- `sum` — total of readings in the bucket
- `avg` — mean
- `min` / `max`
- `last` — last reading in the bucket
- `delta` — `last − first` in the bucket (≥2 readings, else null)

**`delta` is mandatory, not optional.** Plant flow comes from **totalizer** meters (monotonic counters): daily flow = end-of-day reading − start-of-day reading = `delta`. Using `sum` on a totalizer is wrong. The migration variables `var_terfi1_gunluk` / `var_terfi2_gunluk` are totalizer deltas.

`div` additionally takes an `on_zero` policy (`null|zero|fail`); see Validation Rules.

`reduce` collapses a series to one scalar with `sum|avg|min|max|last`. It is required for scalar variables such as "last 7 days average daily flow" where the correct source is a daily `delta` series, not an average of raw totalizer readings.

Quality-policy compatibility matters: the current `daily_rollup` implementation does not filter by `quality`. To preserve legacy Excel behavior, `source_type=tag` keeps the existing all-readings behavior unless that path is explicitly migrated. Variable evaluation can default to `good_only`, but parity tests must compare paths with the same quality policy, or the shared aggregation primitive must be upgraded to accept `quality_policy`.

### Example expressions

Daily total BAAT inflow (two totalizer pumps, daily delta each, then summed):

```json
{
  "op": "add",
  "args": [
    { "op": "agg", "source": { "type": "tag", "tag_id": 101 }, "agg": "delta", "window": "day" },
    { "op": "agg", "source": { "type": "tag", "tag_id": 102 }, "agg": "delta", "window": "day" }
  ]
}
```

Last 7 day average daily inflow from a totalizer:

```json
{
  "op": "reduce",
  "source": {
    "op": "series",
    "source": { "type": "tag", "tag_id": 201 },
    "agg": "delta",
    "grain": "day",
    "window": "7d"
  },
  "reduce": "avg"
}
```

Daily series with 7-day moving average:

```json
{
  "op": "moving_avg",
  "source": {
    "op": "series",
    "source": { "type": "tag", "tag_id": 201 },
    "agg": "delta",
    "grain": "day"
  },
  "window_size": 7
}
```

### Deferred features

Not included in v1:

- conditional logic
- string or boolean variables
- user-defined functions
- free-text expression DSL
- caching or materialized variable snapshots
- extra math ops `pow` / `sqrt` (not needed by the current workbook; add when a report requires them)

### Future enhancements (post-v1)

Evaluated and intentionally deferred — captured so they are not re-discovered later:

- **Draft / Published workflow** — a formula-editing state so an in-progress edit can't be consumed by a concurrently-running scheduled report. *v1 mitigation*: saves are atomic and validate-gated, so a persisted `version` is always internally consistent (never half-finished). The remaining gap — re-pointing a binding to a *new* logic — is acceptable for v1's manual workflow; revisit if scheduled reports + live editing collide in practice.
- **Bulk dependency replace (tag swap)** — when a sensor/PLC is replaced its `tag_id` changes, potentially breaking many variables. A "replace all references `old_tag_id` → `new_tag_id`" admin tool is straightforward on top of `facility_variable_dependencies` (already the normalized index for this). Defer the tooling; the dependency table makes it cheap to add later.
- **Dependency DAG view** — a visual node graph of tag→variable→variable edges. The `/dependencies` endpoint + dependency table already expose the data; v1 ships a flat dependency list, the graph is a UI upgrade.
- **Preview mock / dry-run** — inject synthetic operand values to exercise edge cases (divide-by-zero, null propagation) without hunting a historical date. Useful for validating `on_zero` / `coalesce` logic; defer because it needs a synthetic-source path in the engine.
- **Unit strict mode / auto-conversion** — beyond v1's conservative warn-on-incompatible: enforce dimensional correctness or auto-convert compatible units (`m3`↔`liters`), forcing an explicit `const` multiplier otherwise. Natural follow-up to `facility_variable_units.py`.

## Backend Architecture

Recommended service split:

- `facility_variable_service.py`
  CRUD, validation, dependency extraction
- `facility_variable_engine.py`
  expression evaluation
- `facility_variable_preview.py`
  scalar/series preview responses
- `facility_variable_units.py`
  unit compatibility checks
- `facility_variable_binding.py`
  Excel and report binding resolution

### Evaluation flow

1. Parse `expression_json`
2. Extract dependencies
3. Reject cycles
4. Fetch tag or variable sources (honoring `tz_offset` — see below)
5. Evaluate operation tree
6. Normalize to scalar or series result
7. Apply null and quality policies

### Quality policy propagation (`ref`)

When variable B references variable A via `ref`, two `quality_policy` values meet and the resolution must be deterministic:

- `quality_policy` is applied **at the leaf** — it filters readings when an `agg`/`series` pulls from a *tag*. So each variable's policy governs only the tag reads inside its own expression.
- a `ref` to another variable consumes that variable's **already-computed result**; the referrer does **not** re-apply its own quality policy over the referenced output (the bad readings are already gone or kept per A's policy)
- net effect: each leaf tag read uses the policy of the variable whose expression contains that leaf — there is no hierarchical override, no surprise re-filtering
- document this on the variable form so a user setting B=`good_only` while A=`allow_bad` understands A's bad data still flows through B

### Output shape contract (bridge to existing Excel fill)

This is the load-bearing integration point. The current fill loop (`app/services/template_fill/fill_engine.py`) is **month-based**: it calls `daily_values(db, tag_id, year, month, agg, tz_offset_hours) -> {day_no: value}` and writes each day into `day_to_row`. The variable engine **must produce the same shape** so a `series` variable drops into that loop with no rewrite of the fill path:

- the binding resolver calls the engine with a **(year, month) window at daily grain**
- the engine returns a **`{day_no: value}` dict** (days with no data are absent — no zero-fill, matching `daily_values`)
- the fill loop is otherwise unchanged: same `day_to_row` mapping, same "blank if missing" behavior

A `scalar` variable, or a `series` bound with `write_mode=reduce`, collapses to a single value written to `target_cell`. The `series` op's internal points use epoch/`ts`, but the **Excel-facing contract for column targets is always `{day_no: value}` over the requested month**. The richer `series` preview shape (`{ts, value}` points) is for the API/UI preview only — Excel never consumes raw points.

If the engine and `daily_rollup` ever diverge on the same `(tag, agg, window)`, that is a bug: both paths must route through one shared aggregation primitive. Prefer having the engine **reuse `daily_rollup` / the rollup-routing helpers** rather than re-implementing bucketing.

### Time zone

All bucketing is tz-sensitive. Readings are stored UTC-naive; the existing rollup shifts day boundaries by `settings.REPORT_TZ_OFFSET_HOURS` (local-day semantics). The variable engine **must apply the same offset on every `agg`/`series` bucket boundary**. An engine that buckets in raw UTC will silently disagree with the Excel fill (and with `daily_rollup`) by up to one day at the edges.

- `tz_offset_hours` is an explicit engine input, threaded down to every leaf `agg`/`series`, sourced from `REPORT_TZ_OFFSET_HOURS`
- preview `ts` values are emitted at the **local day boundary** rendered as the configured offset — not bare `Z`/UTC — so the preview matches what lands in the workbook
- a single variable evaluated for Excel fill and for API preview must use one offset; they cannot diverge

### Roll-up sources per grain

`default_time_grain` advertises `hour|day|week|month`, but the materialized continuous aggregates are only `tag_readings_1m/5m/1h/1d`. So:

- **PostgreSQL/Timescale**: `hour` → `tag_readings_1h`, `day` → `tag_readings_1d`. **`week`/`month` are NOT materialized** — the engine composes them by aggregating up from `1d` (re-aggregating daily buckets), the same routing idea as `_rollup_series_window` in `app/api/dashboard.py`. Do not assume a `1w`/`1mo` cagg exists.
- **SQLite/dev**: no caggs at all — fall back to grouping raw `tag_readings` in Python, exactly as `daily_rollup._daily_sqlite` does. Acceptable for dev volumes; wide series previews on raw scans are the slow path (no caching in v1 — see Deferred features).
- `delta` over a coarse grain (week/month) means last−first **of that whole window**, not a sum of daily deltas — define this explicitly per grain so totalizer math stays correct when re-aggregating.

### Archive and workbook metadata

`ReportArchive` currently has `result_json` but no explicit metadata column. Version stamping therefore needs an explicit storage decision in implementation:

- advanced reports add a `variable_refs_json` (or equivalent metadata) field on `report_archive`, and also include the resolved refs in the compressed `result_json` summary for downloaded archive inspection
- direct Excel template generation currently returns a workbook without creating a `ReportArchive`; variable refs must be embedded into a hidden worksheet such as `_scada_metadata`, or Excel template generation must be routed through an archive flow before version stamping can be guaranteed
- every resolved ref records at least `variable_id`, `code`, `version`, and the evaluated window

## API Surface

### Permissions

Mirror the app-wide gating pattern (same as backup, compliance config, Grafana writes):

- read (`GET` list / detail / dependencies / preview) — any authenticated user
- write (`POST` / `PUT` / `DELETE`, validate-then-save) — permission-gated with `require_perm("facility_variable:create|edit|delete")` plus `require_writable` (blocked in demo mode)
- preview is read-only compute; allow any authenticated user, but it must respect the same license feature gate as reports if one applies

**Registering the new permissions is not optional — `require_perm("...")` only *checks* a string; the catalog must *define* it.** `require_perm` resolves through `user_can` → `effective_permissions` → the catalog in `app/core/permissions.py`. A perm string that is not in `ALL_PERMISSIONS` is never granted to any non-admin (admin auto-gets the full set), so the endpoint would 403 for every operator. Each new perm must be added in three places:

1. `app/core/permissions.py` — declare constants (`PERM_FACILITY_VARIABLE_CREATE = "facility_variable:create"`, `…_EDIT`, `…_DELETE`), append them to `ALL_PERMISSIONS`, and set per-role grants in `ROLE_DEFAULTS`: admin `True` for all via the catalog, operator `create=True`, `edit=True`, `delete=False`, viewer `False` for all
2. backend endpoints — `Depends(require_perm(PERM_FACILITY_VARIABLE_*))` using the constants, not raw strings
3. frontend — gate the create/edit/delete UI with explicit checks (`can("facility_variable:create")`, `can("facility_variable:edit")`, `can("facility_variable:delete")`), and add the human labels wherever permissions are listed (Users page permission editor + i18n ×5). `useAuth().can` does exact string matching, not wildcard matching.

Cover the new perms in `tests/test_permissions.py` (role-default matrix + override behavior) so a missing catalog entry fails loudly instead of silently 403-ing in production.

### CRUD

- `GET /api/facility-variables`
- `POST /api/facility-variables`
- `GET /api/facility-variables/{id}`
- `PUT /api/facility-variables/{id}`
- `DELETE /api/facility-variables/{id}`

Delete should be soft in v1 by toggling `is_active=false` — and is subject to the dangling-binding guard (a variable referenced by an enabled Excel column cannot be silently deactivated).

### Validation and preview

- `POST /api/facility-variables/validate`
- `POST /api/facility-variables/{id}/preview`
- `GET /api/facility-variables/{id}/dependencies`

Both `validate` and `preview` take a **request body**, not just a path id:

- `validate` — body is a candidate `expression_json` + `kind` + policies, so an **unsaved** draft can be checked from the wizard before first save (returns the same error set as Validation Rules)
- `preview` — body specifies the **window to evaluate**, since a variable defines a formula, not a fixed time range:

```json
{
  "window": { "type": "month", "year": 2026, "month": 6 },
  "grain": "day",
  "tz_offset_hours": 3
}
```

`window.type` also accepts `last_24h|last_7d|last_30d|custom` (custom → `start`/`end`), matching the existing report time-range vocabulary. `grain`/`tz_offset_hours` default from the variable's `default_time_grain` and `REPORT_TZ_OFFSET_HOURS` when omitted. For Excel-bound preview, callers pass `{type: "month", ...}` + `grain: "day"` to get exactly what the fill will write.

**Preview must be bounded — it is a UI-triggered query and caching is deferred.** A `series` preview over a 1-year window at 1-minute grain scans millions of raw rows on SQLite (and is uncached everywhere in v1), so a careless preview is a self-inflicted DB DoS. The endpoint enforces hard guards, returning `422` rather than running an unbounded scan:

- a cap on `range / grain` = **max output points** (e.g. reject if the window would yield more than a few thousand points)
- a max custom-range span per grain (1-minute grain limited to a short window; coarser grains allow longer)
- a query timeout / row-fetch ceiling on the underlying scan
- these limits apply to **preview only** — Excel fill is already bounded to one month at daily grain

Preview response shapes:

Scalar:

```json
{ "kind": "scalar", "value": 18342.22, "unit": "m3/gun" }
```

Series:

```json
{
  "kind": "series",
  "points": [
    { "ts": "2026-06-01T00:00:00+03:00", "value": 18211.4 },
    { "ts": "2026-06-02T00:00:00+03:00", "value": 17998.1 }
  ],
  "unit": "m3/gun"
}
```

## Validation Rules

- `code` must be unique and stable
- dependency cycles are rejected
- scalar/series type mismatches are rejected
- divide-by-zero behavior must be explicit — every `div` node carries an `on_zero` policy (`null|zero|fail`); a `div` without it is rejected at validation
- aggregate windows must be explicit
- series grain must be explicit
- `tz_offset` must be applied on every bucket boundary (engine and Excel fill share one offset)
- quality policy must be explicit
- null policy must be explicit
- **output-shape lock while bound**: changing a variable's `kind` (`scalar`↔`series`) is **rejected** while any enabled Excel column binds it, because a `write_mode=series`/`target_mode=column` binding silently breaks if the variable starts returning a scalar (and vice-versa). Same impact-view surfacing as the dangling-binding guard — unbind or fix the columns first. Formula edits that keep `kind` are always allowed.

Unit compatibility should be enforced conservatively in v1:

- numeric operations on clearly incompatible units should at least warn
- obviously invalid combinations such as `m3/day + kWh/day` should not save silently

## UI Design

### List screen

Columns:

- code
- name
- kind
- unit
- dependency count
- status
- updated time

Actions:

- edit
- duplicate
- deactivate
- preview

### Create/edit wizard

1. Basic info
2. Source selection
3. Operation selection
4. Window and grain
5. Preview
6. Save

### Expression builder

Use block-based UI, not free text:

- add source
- choose operation
- choose time window
- arithmetic combine
- moving average

This keeps the v1 experience constrained and debuggable.

### Excel mapping UX

Excel column mapping must allow:

- source type selection: `tag` or `variable`
- source picker
- write mode selection for series-backed variables
- reduce operation selection when `write_mode=reduce`
- target mode selection for variable bindings: existing daily column fill or explicit scalar `target_cell`

## Integration Strategy

### Excel templates

Move from direct worksheet formulas to backend-derived variables wherever possible.

Example migration of current workbook logic:

- `var_terfi1_gunluk`
- `var_terfi2_gunluk`
- `var_baat_giris_toplam = terfi1 + terfi2`
- `var_tesis_toplam_debi = aot + baat + kapasite_fazlasi`

Then bind worksheet columns directly:

- `E -> var_aot_gunluk_debi`
- `F -> var_kapasite_fazlasi`
- `K -> var_baat_giris_toplam`
- `M -> var_tesis_toplam_debi`

### Advanced reports

Advanced reports should be extended to select facility variables in addition to raw tags.

Tag-based reports continue to work during migration.

## Migration Plan

### Phase 1

Add the new tables and backend engine. Existing reports remain unchanged.

### Phase 2

Extend `excel_template_columns` with variable-aware binding fields. Preserve current `tag_id + agg` behavior.

### Phase 3

Seed a small set of high-value shared variables, for example:

- total transfer flow
- total plant inflow
- 7-day average inflow

### Phase 4

Expose facility variable CRUD and preview UI.

### Phase 5

Enable Excel template columns to bind to variables.

### Phase 6

Enable advanced reports to bind to facility variables.

### Phase 7

Gradually eliminate workbook-side business formulas in favor of backend variables.

## Testing Strategy

### Backend

- expression validation tests
- cycle detection tests
- scalar preview tests
- series preview tests
- null and quality policy tests
- `div` `on_zero` policy tests (`null`/`zero`/`fail`)
- `round` mode tests matching Excel `ROUND`, especially `.5` edge cases
- shape-alignment tests for scalar/scalar, series/series, series/scalar, and `coalesce` scalar fallback broadcast
- unit compatibility tests
- Excel binding mode tests
- **`delta` totalizer tests** — daily `delta` matches `daily_rollup`; coarse-grain `delta` = window last−first, not sum of daily deltas
- **tz boundary tests** — engine and `daily_rollup` agree at day edges for nonzero `REPORT_TZ_OFFSET_HOURS`
- **permission tests** — write endpoints require the facility-variable permission plus `require_writable`; demo mode blocks writes
- **dangling-binding tests** — deactivating a referenced variable is blocked; fill-time broken binding warns, not blanks
- **preview guard tests** — too many output points, too-wide custom ranges, or raw row ceilings return `422`

### Integration

- variable-backed Excel fill tests
- mixed tag and variable template tests
- advanced report variable rendering tests
- **engine ≡ `daily_rollup` parity** — same `{day:value}` for a `source_type=variable` column wrapping a single tag+agg as the equivalent `source_type=tag` column when both use the same quality policy
- **archive version stamping** — generated archive records resolved `(variable_id, version)`

### Migration safety

- legacy template behavior must remain unchanged when `source_type=tag`

## Risks

- too much formula freedom will increase support cost
- weak unit validation will allow silently wrong variables
- loose scalar/series semantics will make the model inconsistent
- leaving hidden business logic in Excel will undermine backend source-of-truth goals
- **engine/`daily_rollup` divergence** — two aggregation code paths drifting on the same `(tag, agg, window)` ⇒ Excel and preview disagree; mitigated by reusing one shared primitive (see Output shape contract)
- **silent dangling bindings** — deactivating a referenced variable blanks cells without warning; mitigated by the deactivation guard + fill-time warnings
- **recompute drift** — re-running a template after a formula edit changes historical numbers; mitigated by stamping `(variable_id, version)` into the archive (not frozen — no snapshots in v1)
- **wrong totalizer math** — using `sum` instead of `delta`, or summing daily deltas across a coarse grain; mitigated by mandatory explicit `agg` + per-grain `delta` definition

## Recommended v1 Boundaries

- JSON expression tree only
- numeric variables only
- one facility namespace only
- no conditionals
- no custom functions
- no caching

These limits keep the first release implementable while still covering the real workbook-driven reporting needs already visible in `gunluk_rapor.xlsx`.
