# Facility / Water-Quality Generators → frser-sqlite Adaptation — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan

## Problem

The `facility_overview` and `water_quality` Grafana dashboard generators
(`app/services/grafana_templates.py`) emit panels targeting a PostgreSQL
datasource (`{type: "postgres", uid: "timescaledb"}`) and use Grafana's
PostgreSQL macros (`$__timeGroupAlias`, `$__timeFilter`, `$__time`) plus
PostgreSQL-only SQL (`now() - INTERVAL`, `DISTINCT ON`, `EXTRACT(EPOCH ...)`).

The actual deployment Grafana has **no** `timescaledb` datasource — its
configured datasource is **frser-sqlite-datasource** (`uid` from
`settings.GRAFANA_DATASOURCE_UID`, default `scadadb`) pointing at the backend
SQLite. So generated facility/water dashboards render **"No data"**.

The lab generator was already adapted to frser (`build_lab_dashboard`,
`_lab_datasource`, `_frser_target`, `_lab_sql_code`). This change brings the
two remaining project templates to the same datasource and SQL dialect.

## Constraints (verified)

- **frser-sqlite supports NO `$__` macros** (verified empirically:
  `$__timeFilter` / `$__timeFrom` / `$__unixEpoch` all error "missing named
  argument"). Only plain SQL plus fixed time windows
  (`datetime('now', '-24 hours')`).
- frser target shape (mirror `_frser_target`): `{refId, datasource:{type:
  "frser-sqlite-datasource", uid}, queryType: "time series"|"table",
  queryText, rawQueryText, timeColumns:["time"]}`. Epoch time column:
  `CAST(strftime('%s', col) AS INTEGER) AS time`.
- **The report-template generator (`build_report_template_dashboard`) is
  OUT OF SCOPE and must stay byte-for-byte unchanged.** It shares the
  `_timeseries_panel` / `_table_panel` / `_stat_panel` helpers with
  facility/water, so those helpers must remain backward-compatible (their
  current PostgreSQL output is the default; frser is opt-in per call).

## Architecture

### Shared panel helpers — opt-in datasource/target injection

`_timeseries_panel`, `_stat_panel`, `_table_panel` each gain two optional
keyword args with PostgreSQL-preserving defaults:

```python
def _timeseries_panel(..., *, unit="short", datasource=None, target=None) -> dict:
    ...
    "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
    "targets": [target or {"refId": "A", "format": "time_series", "rawSql": raw_sql}],
```

When `datasource`/`target` are omitted (report-template's call sites), output
is identical to today. Facility/water pass `_frser_datasource()` and
`_frser_target(sql, time_series=...)`.

`_lab_datasource()` is renamed to `_frser_datasource()` (it returns the
configured frser datasource — not lab-specific); its three current lab call
sites are updated. No behavior change.

### Facility (`build_facility_overview_dashboard`) — fixed 24h window

All panels become frser targets. SQL conversions:

- **Toplam Tag** (stat): `SELECT count(*) AS "Tag" FROM tags` — dialect-neutral, unchanged SQL, frser table target.
- **Son Okuma** (stat): `EXTRACT(EPOCH FROM max(timestamp)) * 1000` → `CAST(strftime('%s', max(timestamp)) AS INTEGER) * 1000 AS "Son Okuma" FROM tag_readings`.
- **Son 24s Okuma** (stat): `now() - INTERVAL '24 hours'` → `datetime('now', '-24 hours')`.
- **BAD Kalite %** (stat): same window swap.
- **Okuma Hacmi** (timeseries, 5m bucket): `$__timeGroupAlias(timestamp,'5m')` → `(CAST(strftime('%s', timestamp) AS INTEGER) / 300) * 300 AS time`, `WHERE timestamp >= datetime('now','-24 hours')`.
- **BAD Kalite Oranı** (timeseries, 15m bucket): bucket `/ 900 * 900 AS time`, same window.
- **Son Değerler** (table): `DISTINCT ON (t.id) ... ORDER BY t.id, tr.timestamp DESC` → SQLite has no `DISTINCT ON`; use a `row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC)` subquery filtered to `rn = 1`, then `ORDER BY timestamp DESC LIMIT 20`.

### Water (`build_water_quality_dashboard`) — fixed 7d window

- **Su Kalitesi Trendleri** (timeseries): `$__time(tr.timestamp) AS time` → `CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time`; `$__timeFilter(tr.timestamp)` → `tr.timestamp >= datetime('now','-7 days')`; keep `tr.tag_id IN ({ids})`.
- **Son Değerler** (table): `DISTINCT ON` → `row_number()` subquery, `WHERE t.id IN ({ids})`, `rn = 1`.
- **Limit Aşımı Özeti** (table): `$__timeFilter(tr.timestamp)` → `tr.timestamp >= datetime('now','-7 days')`, keep `t.id IN ({ids})`.

The water dashboard's `time` range is set to `{from: "now-7d", to: "now"}`
(facility keeps the base `now-24h`).

`_tag_filter(tag_ids)` (int-coerce + non-empty validation) is reused
unchanged for the water `IN (...)` list — no user-controlled string reaches
SQL.

## Testing (TDD)

`tests/test_grafana_templates.py` is updated and extended:

- **Flip** `test_build_water_quality_dashboard_shape`: assert the trend
  panel's target is a frser target — `datasource.uid ==
  settings.GRAFANA_DATASOURCE_UID`, `datasource.type ==
  "frser-sqlite-datasource"`, `queryText` contains `strftime('%s'`, contains
  `datetime('now','-7 days')`, contains `tr.tag_id IN (1, 2)`, and contains
  **no** `$__`. `test_water_quality_requires_tags` stays (empty tags →
  ValueError, via `_tag_filter`).
- **Add** a facility shape test: `build_dashboard("facility_overview", ...)`
  → every panel's `datasource.type == "frser-sqlite-datasource"`; the
  "Okuma Hacmi" panel SQL contains `/ 300) * 300 AS time` and
  `datetime('now','-24 hours')`; the "Son Değerler" table SQL contains
  `row_number()` and no `DISTINCT ON`; no panel SQL contains `$__` or
  `now() - INTERVAL` or `EXTRACT(EPOCH`.
- **Add** a report-template regression test: build a report-template
  dashboard and assert its panels still use `{type:"postgres",
  uid:"timescaledb"}` and still contain `$__timeFilter` — proving the shared
  helpers' default path is untouched.
- The existing endpoint tests (`test_generate_dashboard_endpoint_writes_to_grafana`,
  `..._requires_tags_for_water_quality`) stay green (they mock Grafana and
  assert the POST happens / 422 on empty tags — datasource-agnostic).

## Verification

After implementation: in the deployment Grafana, generate a
`facility_overview` and a `water_quality` dashboard and confirm panels render
real data (not "No data") against the frser-sqlite datasource. Lab dashboards
(already frser) continue to work unchanged.

## Out of scope (YAGNI)

- The report-template generator (`build_report_template_dashboard`) — unchanged.
- A PostgreSQL/SQLite dual-dialect abstraction (env-switched SQL). The
  deployment is SQLite; emit frser directly. Postgres support, if ever
  needed, is a separate change.
- Continuous-aggregate / rollup tables.
