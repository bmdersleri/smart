# Adapt the Lab Dashboard Generator to frser-sqlite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build_lab_dashboard` emit Grafana panels for the actual deployment datasource (`frser-sqlite-datasource`, uid `scadadb`) with SQLite query syntax, so generated lab dashboards render data here.

**Architecture:** Rewrite the lab-specific panel construction in `app/services/grafana_templates.py` to emit a frser-sqlite datasource block + `queryText`-style targets with epoch-seconds time (`strftime('%s', time)`), WITHOUT touching the shared `_timeseries_panel`/`_table_panel`/`_base_dashboard` helpers (used by the other generators). Add one config setting for the datasource uid.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy; pytest-asyncio; Grafana frser-sqlite-datasource.

## Global Constraints

- Python baseline **3.14**. Backend TDD per-file: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v` (from `scada-reporter/backend`; Python is `python`, venv `.venv/Scripts/python`).
- Lint/type gate: `just check` (ruff + mypy + frontend) before the final commit.
- **Do NOT modify** the shared helpers `_timeseries_panel`, `_table_panel`, `_base_dashboard`, `_stat_panel` — the facility / water-quality / report-template generators depend on them. Only the lab builder changes.
- frser-sqlite panel shape (proven by the working `scada-watchlist` dashboard): datasource `{"type":"frser-sqlite-datasource","uid":"scadadb"}`; target `{"refId","datasource","queryType":"time series"|"table","queryText","rawQueryText","timeColumns":["time"]}`; epoch time via `CAST(strftime('%s', <col>) AS INTEGER) AS time`. NO postgres `rawSql`/`$__timeFilter`/`$__timeGroupAlias`.
- `_lab_sql_code` allowlist (`^[A-Za-z0-9_-]+$`) must still wrap every `point_code`/`param_code` reaching SQL.
- Keep unchanged: min/max threshold lines, `time: now-30d`, uid `sr-lab-{point_id}-{hash}`, `build_lab_dashboard` signature.
- Branch: `master`, commit directly (dev-phase, no PR). Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Drift hazard:** background automation switches the working-tree branch + pollutes the git index. Implementers MUST `git checkout master` at start and before commit, and commit with an EXPLICIT pathspec `git commit -- <files>` (never `git add -A` / bare `git commit`).

---

## Task 1: frser-sqlite lab builder + config + tests

**Files:**
- Modify: `scada-reporter/backend/app/core/config.py`
- Modify: `scada-reporter/backend/app/services/grafana_templates.py`
- Test: `scada-reporter/backend/tests/test_lab_grafana_builder.py`

**Interfaces:**
- Consumes: existing `_lab_sql_code`, `LabParamSpec`, `lab_dashboard_uid`, `_base_dashboard` (dashboard-level only — safe to reuse), `settings`.
- Produces: `_lab_datasource()`, `_frser_target(sql, *, time_series)`; rewritten `_lab_timeseries_panel` + `build_lab_dashboard` table panel emitting frser-sqlite.

- [ ] **Step 1: Add the config setting**

In `scada-reporter/backend/app/core/config.py`, next to the other `GRAFANA_*` settings (around line 115, after `GRAFANA_SA_TOKEN`), add:

```python
    GRAFANA_DATASOURCE_UID: str = "scadadb"  # frser-sqlite datasource uid for lab dashboards
```

- [ ] **Step 2: Update the failing test first**

Edit `scada-reporter/backend/tests/test_lab_grafana_builder.py`. Replace the body of `test_build_lab_dashboard_shape` with frser-sqlite assertions (keep the other tests as-is):

```python
def test_build_lab_dashboard_shape():
    dash = build_lab_dashboard(
        point_id=5, point_code="INLET", point_name="Inlet", params=_params()
    )
    assert dash["uid"] == lab_dashboard_uid(5, [10, 20])
    assert dash["title"] == "Lab — Inlet"
    # one timeseries panel per param + one table panel
    types = [p["type"] for p in dash["panels"]]
    assert types.count("timeseries") == 2
    assert types.count("table") == 1
    # every panel targets the frser-sqlite datasource and queries the view
    for panel in dash["panels"]:
        assert panel["datasource"] == {"type": "frser-sqlite-datasource", "uid": "scadadb"}
        target = panel["targets"][0]
        assert "rawSql" not in target  # frser uses queryText, not postgres rawSql
        sql = target["queryText"]
        assert sql == target["rawQueryText"]
        assert target["timeColumns"] == ["time"]
        assert "v_lab_timeseries" in sql
    # the pH timeseries panel: epoch time + its own codes, no postgres macros
    ph = next(p for p in dash["panels"] if p["title"].startswith("pH"))
    ph_sql = ph["targets"][0]["queryText"]
    assert ph["targets"][0]["queryType"] == "time series"
    assert "CAST(strftime('%s', time) AS INTEGER) AS time" in ph_sql
    assert "point_code = 'INLET'" in ph_sql
    assert "param_code = 'PH'" in ph_sql
    assert "$__timeFilter" not in ph_sql
    # the table panel
    table = next(p for p in dash["panels"] if p["type"] == "table")
    assert table["targets"][0]["queryType"] == "table"
    assert "param_code IN (" in table["targets"][0]["queryText"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_builder.py::test_build_lab_dashboard_shape -p no:randomly -n0 -v`
Expected: FAIL — the current builder emits the postgres datasource + `rawSql`.

- [ ] **Step 4: Rewrite the lab builder**

In `scada-reporter/backend/app/services/grafana_templates.py`:

1. Add the settings import at the top (the module currently imports only `hashlib`, `re`, `dataclass`, `Literal`):

```python
from app.core.config import settings
```

2. Add the two frser helpers just above `_lab_timeseries_panel` (after `lab_dashboard_uid`):

```python
def _lab_datasource() -> dict:
    return {"type": "frser-sqlite-datasource", "uid": settings.GRAFANA_DATASOURCE_UID}


def _frser_target(sql: str, *, time_series: bool) -> dict:
    return {
        "refId": "A",
        "datasource": _lab_datasource(),
        "queryType": "time series" if time_series else "table",
        "queryText": sql,
        "rawQueryText": sql,
        "timeColumns": ["time"],
    }
```

3. Replace the entire `_lab_timeseries_panel` function with the frser version:

```python
def _lab_timeseries_panel(panel_id: int, point_code: str, param: LabParamSpec, *, y: int) -> dict:
    """A v_lab_timeseries (frser-sqlite) time-series panel for one parameter, with limit lines."""
    sql = (
        f"SELECT CAST(strftime('%s', time) AS INTEGER) AS time, param_name AS metric, value "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code = {_lab_sql_code(param.code)} "
        f"ORDER BY time"
    )
    title = f"{param.name}{f' ({param.unit})' if param.unit else ''}"
    steps: list[dict] = [{"color": "green", "value": None}]
    if param.min_limit is not None:
        steps.append({"color": "orange", "value": param.min_limit})
    if param.max_limit is not None:
        steps.append({"color": "red", "value": param.max_limit})
    # Grafana wants steps sorted ascending; the base None step stays first.
    steps[1:] = sorted(steps[1:], key=lambda s: s["value"])
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": _lab_datasource(),
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 8},
        "fieldConfig": {
            "defaults": {
                "unit": param.unit or "short",
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "showPoints": "always",
                    "pointSize": 6,
                    "spanNulls": True,
                    "thresholdsStyle": {"mode": "line"},
                },
                "color": {"mode": "palette-classic"},
                "thresholds": {"mode": "absolute", "steps": steps},
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
        "targets": [_frser_target(sql, time_series=True)],
    }
```

4. Replace the table-panel construction inside `build_lab_dashboard` (the `codes_in`/`table_sql`/`_table_panel(...)` block) with the frser table panel:

```python
    # latest-values table across the whole selection
    codes_in = ", ".join(_lab_sql_code(p.code) for p in params)
    table_sql = (
        f"SELECT time, param_name, value, unit, min_limit, max_limit "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code IN ({codes_in}) "
        f"ORDER BY time DESC LIMIT 200"
    )
    panels.append(
        {
            "id": len(params) + 1,
            "type": "table",
            "title": "Son değerler",
            "datasource": _lab_datasource(),
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 10},
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {"showHeader": True},
            "targets": [_frser_target(table_sql, time_series=False)],
        }
    )
```

Leave the rest of `build_lab_dashboard` unchanged (the empty-`params` ValueError, the per-param loop calling `_lab_timeseries_panel`, the uid, `_base_dashboard(uid, f"Lab — {point_name}", ["lab"], panels)`, and `dash["time"] = {"from":"now-30d","to":"now"}`).

- [ ] **Step 5: Run the builder tests**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_builder.py -p no:randomly -n0 -v`
Expected: PASS (all — the updated shape test + the unchanged threshold/time-window/allowlist/uid tests).

- [ ] **Step 6: Run the endpoint tests (ensure still green)**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_api.py -p no:randomly -n0 -v`
Expected: PASS. The endpoint tests assert status mapping + panel count (3) + `overwrite: True`, not the datasource type. If any assertion references `rawSql`/postgres, update it to the frser equivalent (it should not).

- [ ] **Step 7: Checks + commit**

Run: `.venv/Scripts/python -m ruff check app/services/grafana_templates.py app/core/config.py` (clean), then `just check` — confirm no NEW failure traces to these files.

```bash
git checkout master
git commit -- scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/app/core/config.py scada-reporter/backend/tests/test_lab_grafana_builder.py -m "feat(lab-grafana): emit frser-sqlite panels for the lab dashboard generator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(If pre-commit reformats, re-run the same `git commit --` with the same paths.)

---

## Task 2: End-to-end verification + doc

**Files:**
- Modify: `docs/lab-data-entry.md` (update the dashboard-generator subsection's datasource note)

- [ ] **Step 1: Full backend suite**

Run (from `scada-reporter/backend`): `just test`
Expected: all pass, including `test_lab_grafana_builder.py` and `test_lab_grafana_api.py`. (A pre-existing, non-lab bandit B608 warning may remain — out of scope.)

- [ ] **Step 2: Regenerate + confirm data renders**

With the backend reachable and the lab data present (the dev SQLite has lab samples for "Havalandırma Havuzu 1" with İletkenlik/BOI), regenerate via the API (admin token from `POST /api/auth/token` form-data admin/admin123):

```bash
curl.exe -s -X POST http://localhost:8001/api/grafana/dashboards/from-lab \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"sample_point_id":4,"parameter_ids":[2,4]}'
```
Then fetch the written dashboard from Grafana (`curl.exe -u admin:admin123 http://localhost:3000/api/dashboards/uid/<uid>`) and confirm every panel's `datasource.type` is `frser-sqlite-datasource` and the `targets[0].queryText` contains `strftime`. In the browser (Monitoring & Analytics) open the regenerated dashboard tab and confirm the İletkenlik/BOI panels render data (not "No data").

> NOTE: loading the new `/from-lab` output requires the running backend to have the rebuilt code. The NSSM `EkontBackend` service has no hot-reload; if it serves stale code, the generated panels will still be postgres — restart the service (needs elevation/UAC) before this check, or run the builder in-process to confirm.

- [ ] **Step 3: Update the doc**

In `docs/lab-data-entry.md`, in the "Generate a Grafana Dashboard from a Selection" subsection, replace the Postgres/TimescaleDB-datasource caveat with the actual behavior: generated lab dashboards target the `frser-sqlite-datasource` (uid from `GRAFANA_DATASOURCE_UID`, default `scadadb`) reading the SQLite `v_lab_timeseries` view directly; note that moving to PostgreSQL later would require re-introducing the postgres dialect for the lab generator.

- [ ] **Step 4: Commit + push**

```bash
git checkout master
git commit -- docs/lab-data-entry.md -m "docs(lab-grafana): lab dashboards use the frser-sqlite datasource

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master
```

---

## Self-Review

**Spec coverage:**
- Lab generator → frser-sqlite datasource + SQLite SQL → Task 1 (`_lab_datasource`, `_frser_target`, rewritten `_lab_timeseries_panel` + table). ✓
- Config `GRAFANA_DATASOURCE_UID` (default `scadadb`) → Task 1 Step 1. ✓
- Shared helpers untouched; other generators untouched → Task 1 only edits the lab-local builder + adds new helpers. ✓
- `_lab_sql_code` allowlist still wraps codes → preserved in the rewritten SQL. ✓
- Thresholds / `now-30d` / uid / signature unchanged → preserved. ✓
- Tests updated to frser shape → Task 1 Step 2. ✓
- Doc updated → Task 2 Step 3. ✓

**Placeholder scan:** No "TBD"/"implement later". All code shown in full.

**Type consistency:** `_lab_datasource() -> dict` and `_frser_target(sql, *, time_series: bool) -> dict` used identically in `_lab_timeseries_panel` and the table block. `build_lab_dashboard` signature, `lab_dashboard_uid`, `LabParamSpec`, `_lab_sql_code` all unchanged and consistent with their existing definitions. The test asserts the exact datasource dict `{"type":"frser-sqlite-datasource","uid":"scadadb"}` matching `_lab_datasource()` with the default config value.
