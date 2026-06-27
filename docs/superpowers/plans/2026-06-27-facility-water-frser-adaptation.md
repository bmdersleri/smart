# Facility / Water-Quality Generators → frser-sqlite Adaptation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the `facility_overview` and `water_quality` Grafana generators emit frser-sqlite panels (the deployment datasource) so they render real data instead of "No data".

**Architecture:** Add opt-in `datasource`/`target` kwargs (PostgreSQL-preserving defaults) to the shared `_timeseries_panel`/`_stat_panel`/`_table_panel` helpers; rename `_lab_datasource`→`_frser_datasource`; rewrite the two builders to pass frser targets with fixed-window SQLite SQL. The report-template generator keeps the default (PostgreSQL) path untouched.

**Tech Stack:** Python 3.14, FastAPI, pytest-asyncio, Grafana frser-sqlite-datasource.

## Global Constraints

- frser-sqlite supports NO `$__` macros — use plain SQL + fixed windows `datetime('now', '-N units')`. Epoch time column: `CAST(strftime('%s', col) AS INTEGER) AS time`.
- frser target via existing `_frser_target(sql, *, time_series)`; datasource via `_frser_datasource()` (uid = `settings.GRAFANA_DATASOURCE_UID`, type `frser-sqlite-datasource`).
- `build_report_template_dashboard` MUST stay byte-for-byte unchanged: the shared helpers' default (no `datasource`/`target` kwarg) output identical PostgreSQL panels.
- `_tag_filter(tag_ids)` (int-coerce + non-empty ValueError) reused unchanged — no user string reaches SQL.
- SQLite quoting in Python: for SQL containing single-quote literals (`'%s'`, `'-24 hours'`), use double-quoted Python strings and escape SQL identifiers as `\"Name\"` (matches the file's existing style).
- TDD per-file from `scada-reporter/backend`: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py -p no:randomly -n0 -v`.
- Commit: `git checkout master` first; `-m "msg"` BEFORE `--`; explicit pathspec; never `git add -A`; never force-push; footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Helper injection + `_frser_datasource` rename + facility builder

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py`
- Test: `scada-reporter/backend/tests/test_grafana_templates.py`

**Interfaces:**
- Produces: `_frser_datasource() -> dict`; `_timeseries_panel(..., *, unit="short", datasource=None, target=None)`; `_stat_panel(..., *, datasource=None, target=None)`; `_table_panel(..., *, datasource=None, target=None)`; rewritten `build_facility_overview_dashboard(uid, title)` emitting frser panels.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_grafana_templates.py` (keep existing imports; add `from app.core.config import settings` and `from app.services.grafana_templates import build_facility_overview_dashboard, build_report_template_dashboard` to the existing import line as needed):

```python
def test_build_facility_dashboard_is_frser():
    dash = build_dashboard("facility_overview", "sr-fac-x", "Tesis")
    assert "facility-overview" in dash["tags"]
    for panel in dash["panels"]:
        assert panel["datasource"]["type"] == "frser-sqlite-datasource"
        assert panel["datasource"]["uid"] == settings.GRAFANA_DATASOURCE_UID
        tgt = panel["targets"][0]
        assert "$__" not in tgt["queryText"]
        assert "now() - INTERVAL" not in tgt["queryText"]
        assert "EXTRACT(EPOCH" not in tgt["queryText"]
    sqls = {p["title"]: p["targets"][0]["queryText"] for p in dash["panels"]}
    assert "/ 300) * 300 AS time" in sqls["Okuma Hacmi"]
    assert "datetime('now', '-24 hours')" in sqls["Okuma Hacmi"]
    assert "row_number()" in sqls["Son Değerler"]
    assert "DISTINCT ON" not in sqls["Son Değerler"]


def test_report_template_dashboard_still_postgres():
    dash = build_report_template_dashboard(
        template_id=1, title="Rapor", tag_ids=[1, 2],
        time_range_type="last_24h", show_trend_charts=True,
        show_summary_stats=True, anomaly_enabled=False, show_anomaly_table=False,
    )
    trend = dash["panels"][0]
    assert trend["datasource"] == {"type": "postgres", "uid": "timescaledb"}
    assert "$__timeFilter" in trend["targets"][0]["rawSql"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py::test_build_facility_dashboard_is_frser tests/test_grafana_templates.py::test_report_template_dashboard_still_postgres -p no:randomly -n0 -v`
Expected: `test_build_facility_dashboard_is_frser` FAILS (panels are postgres / `targets[0]` has `rawSql` not `queryText`); `test_report_template_dashboard_still_postgres` PASSES (it documents current behavior — a regression guard).

- [ ] **Step 3: Add `datasource`/`target` kwargs to the three shared helpers**

In `_timeseries_panel`, change the signature line `unit: str = "short",` to also accept the two kwargs, and change the `datasource` + `targets` lines:

```python
def _timeseries_panel(
    panel_id: int,
    title: str,
    raw_sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    unit: str = "short",
    datasource: dict | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 1,
                    "fillOpacity": 8,
                    "showPoints": "never",
                    "spanNulls": True,
                },
                "color": {"mode": "palette-classic"},
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "right",
                "calcs": ["last", "min", "max"],
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [target or {"refId": "A", "format": "time_series", "rawSql": raw_sql}],
    }
```

In `_stat_panel`, add `datasource: dict | None = None, target: dict | None = None` to the keyword-only args and change:
```python
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
```
```python
        "targets": [target or {"refId": "A", "format": "table", "rawSql": raw_sql}],
```

In `_table_panel`, add the same two kwargs and change:
```python
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
```
```python
        "targets": [target or {"refId": "A", "format": "table", "rawSql": raw_sql}],
```

- [ ] **Step 4: Rename `_lab_datasource` → `_frser_datasource`**

Rename the function (line ~343) and update its three call sites:

```python
def _frser_datasource() -> dict:
    return {"type": "frser-sqlite-datasource", "uid": settings.GRAFANA_DATASOURCE_UID}
```

In `_frser_target` change `"datasource": _lab_datasource(),` → `"datasource": _frser_datasource(),`.
In `_lab_timeseries_panel` change `"datasource": _lab_datasource(),` → `"datasource": _frser_datasource(),`.
In `build_lab_dashboard`'s table panel change `"datasource": _lab_datasource(),` → `"datasource": _frser_datasource(),`.
(Confirm no other `_lab_datasource` references remain: grep returns none.)

- [ ] **Step 5: Rewrite `build_facility_overview_dashboard`**

Replace the whole function body (lines ~169-252) with:

```python
def build_facility_overview_dashboard(uid: str, title: str) -> dict:
    ds = _frser_datasource()
    tag_count_sql = 'SELECT count(*) AS "Tag" FROM tags'
    last_read_sql = (
        "SELECT CAST(strftime('%s', max(timestamp)) AS INTEGER) * 1000 "
        "AS \"Son Okuma\" FROM tag_readings"
    )
    reads_24h_sql = (
        "SELECT count(*) AS \"Okuma\" FROM tag_readings "
        "WHERE timestamp >= datetime('now', '-24 hours')"
    )
    bad_pct_sql = (
        "SELECT 100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
        "/ NULLIF(count(*), 0) AS \"BAD %\" FROM tag_readings "
        "WHERE timestamp >= datetime('now', '-24 hours')"
    )
    volume_sql = (
        "SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 300) * 300 AS time, "
        "count(*) AS \"Okuma\" FROM tag_readings "
        "WHERE timestamp >= datetime('now', '-24 hours') GROUP BY 1 ORDER BY 1"
    )
    bad_rate_sql = (
        "SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 900) * 900 AS time, "
        "100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
        "/ NULLIF(count(*), 0) AS \"BAD %\" FROM tag_readings "
        "WHERE timestamp >= datetime('now', '-24 hours') GROUP BY 1 ORDER BY 1"
    )
    last_values_sql = (
        "SELECT name, device, value, unit, quality, timestamp FROM ("
        "SELECT t.name, t.device, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id"
        ") WHERE rn = 1 ORDER BY timestamp DESC LIMIT 20"
    )
    return _base_dashboard(
        uid,
        title,
        ["facility-overview"],
        [
            _stat_panel(
                1, "Toplam Tag", tag_count_sql, x=0, y=0, w=6, h=5,
                datasource=ds, target=_frser_target(tag_count_sql, time_series=False),
            ),
            _stat_panel(
                2, "Son Okuma", last_read_sql, x=6, y=0, w=6, h=5,
                datasource=ds, target=_frser_target(last_read_sql, time_series=False),
            ),
            _stat_panel(
                3, "Son 24s Okuma", reads_24h_sql, x=12, y=0, w=6, h=5,
                datasource=ds, target=_frser_target(reads_24h_sql, time_series=False),
            ),
            _stat_panel(
                4, "BAD Kalite %", bad_pct_sql, x=18, y=0, w=6, h=5,
                datasource=ds, target=_frser_target(bad_pct_sql, time_series=False),
            ),
            _timeseries_panel(
                5, "Okuma Hacmi", volume_sql, x=0, y=5, w=12, h=8,
                datasource=ds, target=_frser_target(volume_sql, time_series=True),
            ),
            _timeseries_panel(
                6, "BAD Kalite Oranı", bad_rate_sql, x=12, y=5, w=12, h=8,
                unit="percent",
                datasource=ds, target=_frser_target(bad_rate_sql, time_series=True),
            ),
            _table_panel(
                7, "Son Değerler", last_values_sql, x=0, y=13, w=24, h=8,
                datasource=ds, target=_frser_target(last_values_sql, time_series=False),
            ),
        ],
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py -p no:randomly -n0 -v`
Expected: the new facility test PASSES, the report-template regression PASSES, and the existing water test (`test_build_water_quality_dashboard_shape`) STILL ASSERTS postgres — it will still pass here because Task 1 does not touch the water builder. All green.

- [ ] **Step 7: Checks**

Run: `.venv/Scripts/python -m ruff check app/services/grafana_templates.py` (clean) then `.venv/Scripts/python -m pytest tests/test_lab_grafana_builder.py -p no:randomly -n0 -v` (lab builder still green after the rename).

- [ ] **Step 8: Commit**

```bash
git checkout master
git commit -m "feat(grafana): facility generator emits frser-sqlite panels" -- scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_templates.py
```

---

### Task 2: Water-quality builder → frser

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py`
- Test: `scada-reporter/backend/tests/test_grafana_templates.py`

**Interfaces:**
- Consumes: `_frser_datasource`, `_frser_target`, `_tag_filter`, `_timeseries_panel`/`_table_panel` (with the Task 1 kwargs).
- Produces: rewritten `build_water_quality_dashboard(uid, title, tag_ids)` emitting frser panels with a 7-day window.

- [ ] **Step 1: Flip the existing water shape test**

In `tests/test_grafana_templates.py`, replace the body of `test_build_water_quality_dashboard_shape` with:

```python
def test_build_water_quality_dashboard_shape():
    uid = dashboard_uid("water_quality", 3, "Su Kalitesi Hat 1", [2, 1])
    dashboard = build_dashboard("water_quality", uid, "Su Kalitesi Hat 1", [2, 1])
    assert dashboard["uid"] == uid
    assert "water-quality" in dashboard["tags"]
    assert dashboard["time"] == {"from": "now-7d", "to": "now"}
    trend = dashboard["panels"][0]
    assert trend["datasource"]["type"] == "frser-sqlite-datasource"
    assert trend["datasource"]["uid"] == settings.GRAFANA_DATASOURCE_UID
    sql = trend["targets"][0]["queryText"]
    assert "tr.tag_id IN (1, 2)" in sql
    assert "$__" not in sql
    assert "strftime('%s'" in sql
    assert "datetime('now', '-7 days')" in sql
    # latest-values table uses a window function, not DISTINCT ON
    table_sql = dashboard["panels"][1]["targets"][0]["queryText"]
    assert "row_number()" in table_sql
    assert "DISTINCT ON" not in table_sql
```

(`test_water_quality_requires_tags` stays unchanged — empty tags still raise ValueError via `_tag_filter`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py::test_build_water_quality_dashboard_shape -p no:randomly -n0 -v`
Expected: FAIL — current water builder emits postgres `rawSql` with `$__timeFilter`, so `targets[0]["queryText"]` raises KeyError / assertions fail.

- [ ] **Step 3: Rewrite `build_water_quality_dashboard`**

Replace the whole function body (lines ~255-309) with:

```python
def build_water_quality_dashboard(uid: str, title: str, tag_ids: list[int]) -> dict:
    ids = _tag_filter(tag_ids)
    ds = _frser_datasource()
    trend_sql = (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        "t.name AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND tr.tag_id IN ({ids}) "
        "ORDER BY time"
    )
    latest_sql = (
        "SELECT name, value, unit, quality, timestamp FROM ("
        "SELECT t.id AS tid, t.name, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE t.id IN ({ids})"
        ") WHERE rn = 1 ORDER BY tid"
    )
    breach_sql = (
        "SELECT t.name, "
        "sum(CASE WHEN t.min_alarm IS NOT NULL "
        "AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS \"Alt Limit\", "
        "sum(CASE WHEN t.max_alarm IS NOT NULL "
        "AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS \"Üst Limit\" "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND t.id IN ({ids}) "
        "GROUP BY t.name ORDER BY t.name"
    )
    dash = _base_dashboard(
        uid,
        title,
        ["water-quality"],
        [
            _timeseries_panel(
                1, "Su Kalitesi Trendleri", trend_sql, x=0, y=0, w=24, h=11,
                datasource=ds, target=_frser_target(trend_sql, time_series=True),
            ),
            _table_panel(
                2, "Son Değerler", latest_sql, x=0, y=11, w=12, h=8,
                datasource=ds, target=_frser_target(latest_sql, time_series=False),
            ),
            _table_panel(
                3, "Limit Aşımı Özeti", breach_sql, x=12, y=11, w=12, h=8,
                datasource=ds, target=_frser_target(breach_sql, time_series=False),
            ),
        ],
    )
    dash["time"] = {"from": "now-7d", "to": "now"}
    return dash
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py -p no:randomly -n0 -v`
Expected: all PASS (water shape flipped + facility + report-template regression + endpoint tests + requires-tags).

- [ ] **Step 5: Checks**

Run: `.venv/Scripts/python -m ruff check app/services/grafana_templates.py` (clean). Then full module sanity: `.venv/Scripts/python -m pytest tests/test_grafana_templates.py tests/test_lab_grafana_builder.py -p no:randomly -n0 -v` (all green).

- [ ] **Step 6: Commit + push**

```bash
git checkout master
git commit -m "feat(grafana): water-quality generator emits frser-sqlite panels" -- scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_templates.py
git push origin master
```

- [ ] **Step 7: E2E (browser, controller-run)** — generate a `facility_overview` and a `water_quality` dashboard via the UI/endpoint against the deployment Grafana; confirm panels render real data (not "No data"). Needs no backend restart if the builder change is picked up by the running service — but the generate endpoint runs in-process, so an `EkontBackend` restart (UAC) loads the new builder.

---

## Self-Review

**Spec coverage:** datasource swap (both builders) ✓ Task 1/2; `$__` macro removal + fixed windows ✓; `DISTINCT ON`→`row_number()` ✓ both tables; facility 24h / water 7d windows ✓; report-template untouched (default path + regression test) ✓; `_tag_filter` reuse ✓; frser target shape via `_frser_target` ✓.

**Placeholder scan:** none — every SQL string and helper change is complete code.

**Type consistency:** `_frser_datasource()` replaces `_lab_datasource()` everywhere (Task 1 Step 4); the three helpers' new kwargs (`datasource`, `target`) are consumed identically by facility (Task 1) and water (Task 2); `_frser_target(sql, *, time_series)` signature matches existing definition; panel titles in tests (`"Okuma Hacmi"`, `"Son Değerler"`) match the builder titles exactly.
