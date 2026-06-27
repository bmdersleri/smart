# Adapt the Lab Dashboard Generator to the frser-sqlite Datasource — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan
**Builds on:** the lab dashboard generator (`build_lab_dashboard` in `app/services/grafana_templates.py`, endpoint `POST /api/grafana/dashboards/from-lab`).

## Problem

The lab dashboard generator emits Grafana panels targeting a PostgreSQL/
TimescaleDB datasource (`{"type":"postgres","uid":"timescaledb"}`) with
postgres SQL (`rawSql` + `$__timeFilter`). But this deployment has no
`timescaledb` datasource: the backend runs on **SQLite**
(`scada_reporter.db`; PostgreSQL on `:5432` is not running), and Grafana reads
that same SQLite file through the **`frser-sqlite-datasource`** plugin
(datasource uid `scadadb`). As a result, generated lab dashboards show
"No data" even though the lab data exists in the view. A hand-built frser-sqlite
dashboard (`sr-lab-4`) was verified to render the data, confirming the only gap
is the datasource + query dialect the generator emits.

## Scope (from brainstorming)

- **Only the lab generator** is adapted. The other generators
  (`build_facility_overview_dashboard`, `build_water_quality_dashboard`,
  `build_report_template_dashboard`) are NOT touched — they keep their current
  postgres output. The shared panel helpers (`_timeseries_panel`,
  `_table_panel`, `_base_dashboard`, `_stat_panel`) are used by those
  generators and MUST NOT change.
- No postgres↔sqlite dialect-switching layer (YAGNI — postgres is not the
  deployment). The lab generator emits frser-sqlite directly.

## Architecture

### Config (`app/core/config.py`)

Add one setting next to the other `GRAFANA_*` settings:

```python
GRAFANA_DATASOURCE_UID: str = "scadadb"  # frser-sqlite datasource uid for lab dashboards
```

This makes the datasource uid configurable without hardcoding the deployment
value; the type is fixed to `frser-sqlite-datasource`.

### Builder (`app/services/grafana_templates.py`)

`build_lab_dashboard` and `_lab_timeseries_panel` are rewritten to emit
frser-sqlite panels. Because the shared `_timeseries_panel`/`_table_panel`
helpers emit the postgres datasource + `rawSql` target, the lab builder
constructs its panels WITHOUT those helpers (lab-local panel construction).

A small local helper builds the frser datasource block and target:

```
_lab_datasource() -> {"type": "frser-sqlite-datasource", "uid": settings.GRAFANA_DATASOURCE_UID}

_frser_target(sql: str, *, time_series: bool) -> dict:
    return {
        "refId": "A",
        "datasource": _lab_datasource(),
        "queryType": "time series" if time_series else "table",
        "queryText": sql,
        "rawQueryText": sql,
        "timeColumns": ["time"],
    }
```

**`_lab_timeseries_panel(panel_id, point_code, param, *, y)`** — a timeseries
panel for one parameter:

- SQL (epoch-seconds time column, codes via the existing `_lab_sql_code`
  allowlist):
  ```sql
  SELECT CAST(strftime('%s', time) AS INTEGER) AS time, param_name AS metric, value
  FROM v_lab_timeseries
  WHERE point_code = '<point_code>' AND param_code = '<param.code>'
  ORDER BY time
  ```
- No `$__timeFilter` — the proven frser pattern; lab data is sparse and Grafana
  filters the display by the panel's time range.
- panel dict: `type: "timeseries"`, the frser datasource, `gridPos` (w=24,h=8),
  unit from `param.unit or "short"`, the min/max **threshold lines** in
  `fieldConfig.defaults.thresholds` (mode absolute, ascending steps, base
  green/None first) + `custom.thresholdsStyle = {"mode":"line"}` — unchanged
  from the current implementation.
- target: `_frser_target(sql, time_series=True)`.

**Latest-values table** — a `type: "table"` panel:

- SQL:
  ```sql
  SELECT time, param_name, value, unit, min_limit, max_limit
  FROM v_lab_timeseries
  WHERE point_code = '<point_code>' AND param_code IN ('<code>', ...)
  ORDER BY time DESC LIMIT 200
  ```
- target: `_frser_target(sql, time_series=False)`.

**`build_lab_dashboard(*, point_id, point_code, point_name, params)`** —
unchanged signature and behavior except the panels are now frser-sqlite. It
still: raises `ValueError` on empty `params` or a bad code; one timeseries panel
per param stacked vertically + one table panel; uid via `lab_dashboard_uid`;
title `f"Lab — {point_name}"`; `time = {"from":"now-30d","to":"now"}`. The
dashboard is assembled with `_base_dashboard(uid, title, ["lab"], panels)` (that
helper only sets dashboard-level fields — uid/title/tags/time/schemaVersion — and
does not impose a datasource, so it is safe to reuse).

### Endpoint

`POST /api/grafana/dashboards/from-lab` is unchanged — it calls
`build_lab_dashboard` and writes to Grafana via the existing flow.

## Testing (TDD)

Update `tests/test_lab_grafana_builder.py` (the existing builder tests assert the
postgres datasource + `rawSql`; those assertions change):

- `test_build_lab_dashboard_shape`: every panel's datasource is
  `{"type":"frser-sqlite-datasource","uid":"scadadb"}`; every target has
  `queryText` (not `rawSql`) referencing `v_lab_timeseries`; the per-param panel
  filters `point_code = '...'` and `param_code = '...'` and selects
  `CAST(strftime('%s', time) AS INTEGER) AS time`; timeseries targets have
  `queryType == "time series"` and `timeColumns == ["time"]`; the table target
  has `queryType == "table"`.
- `test_limits_become_threshold_lines`: unchanged (thresholds still applied).
- `test_lab_dashboard_time_window`: unchanged (`now-30d`).
- `test_lab_sql_code_allowlist` / `test_bad_code_raises`: unchanged (allowlist
  still guards point/param codes).
- `lab_dashboard_uid` tests: unchanged.

The endpoint tests (`tests/test_lab_grafana_api.py`) assert status mapping +
panel count (3), not the datasource type, so they should still pass; if any
assert `rawSql`/postgres, update them.

## Verification

After implementation: regenerate the lab dashboard for a sample point with data
(e.g. "Havalandırma Havuzu 1") via the Monitoring & Analytics generator and
confirm the panels render data in Grafana (the generator now produces the same
working frser-sqlite output as the hand-built `sr-lab-4`).

## Out of scope (YAGNI)

- A postgres↔sqlite dialect-switching abstraction (`GRAFANA_DATASOURCE_TYPE`).
- Adapting the facility / water-quality / report-template generators.
- A `$__timeFilter` server-side time window on the lab queries.
- Changing the shared panel helpers.

## Notes / limitations

- The lab generator is now coupled to the `frser-sqlite-datasource` (the actual
  deployment). If the project later moves to PostgreSQL/TimescaleDB, the lab
  generator would need the postgres dialect re-introduced (a future
  config-switchable layer — explicitly deferred here).
- `v_lab_timeseries.time` is the SQLite datetime text of `sampled_at`;
  `strftime('%s', time)` yields epoch seconds, which `timeColumns:["time"]`
  tells frser to treat as the time axis.
