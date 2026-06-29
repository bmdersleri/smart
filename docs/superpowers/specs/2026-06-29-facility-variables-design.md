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

Backward compatibility rule:

- if `source_type=tag`, existing `tag_id + agg` behavior continues
- if `source_type=variable`, the variable engine is used

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
- `series`
- `moving_avg`
- `ref`

### Example expressions

Daily total BAAT inflow:

```json
{
  "op": "add",
  "args": [
    { "op": "agg", "source": { "type": "tag", "tag_id": 101 }, "agg": "sum", "window": "day" },
    { "op": "agg", "source": { "type": "tag", "tag_id": 102 }, "agg": "sum", "window": "day" }
  ]
}
```

Last 7 day average inflow:

```json
{
  "op": "agg",
  "source": { "type": "tag", "tag_id": 201 },
  "agg": "avg",
  "window": "7d"
}
```

Daily series with 7-day moving average:

```json
{
  "op": "moving_avg",
  "source": {
    "op": "series",
    "source": { "type": "tag", "tag_id": 201 },
    "agg": "sum",
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
4. Fetch tag or variable sources
5. Evaluate operation tree
6. Normalize to scalar or series result
7. Apply null and quality policies

## API Surface

### CRUD

- `GET /api/facility-variables`
- `POST /api/facility-variables`
- `GET /api/facility-variables/{id}`
- `PUT /api/facility-variables/{id}`
- `DELETE /api/facility-variables/{id}`

Delete should be soft in v1 by toggling `is_active=false`.

### Validation and preview

- `POST /api/facility-variables/validate`
- `POST /api/facility-variables/{id}/preview`
- `GET /api/facility-variables/{id}/dependencies`

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
    { "ts": "2026-06-01T00:00:00Z", "value": 18211.4 },
    { "ts": "2026-06-02T00:00:00Z", "value": 17998.1 }
  ],
  "unit": "m3/gun"
}
```

## Validation Rules

- `code` must be unique and stable
- dependency cycles are rejected
- scalar/series type mismatches are rejected
- divide-by-zero behavior must be explicit
- aggregate windows must be explicit
- series grain must be explicit
- quality policy must be explicit
- null policy must be explicit

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
- unit compatibility tests
- Excel binding mode tests

### Integration

- variable-backed Excel fill tests
- mixed tag and variable template tests
- advanced report variable rendering tests

### Migration safety

- legacy template behavior must remain unchanged when `source_type=tag`

## Risks

- too much formula freedom will increase support cost
- weak unit validation will allow silently wrong variables
- loose scalar/series semantics will make the model inconsistent
- leaving hidden business logic in Excel will undermine backend source-of-truth goals

## Recommended v1 Boundaries

- JSON expression tree only
- numeric variables only
- one facility namespace only
- no conditionals
- no custom functions
- no caching

These limits keep the first release implementable while still covering the real workbook-driven reporting needs already visible in `gunluk_rapor.xlsx`.
