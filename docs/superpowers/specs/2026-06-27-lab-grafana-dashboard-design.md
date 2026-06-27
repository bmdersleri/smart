# Generate Grafana Dashboards from Lab Data — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan
**Builds on:** the Lab Data Entry feature (`v_lab_timeseries` view, `lab_parameters`, `lab_sample_points`) and the existing report-template → Grafana dashboard generator (`app/api/grafana_dashboards.py`, `app/services/grafana_templates.py`).

## Problem

Lab measurement data is entered through the Lab Data Entry screen and stored in
the `lab_*` tables, exposed to Grafana via the `v_lab_timeseries` view. There is
a single provisioned `lab-quality` dashboard with point/parameter template
variables, but no way to **generate a concrete, saved Grafana dashboard** for a
specific selection of sample point + parameters — the way report templates can
already be turned into dashboards. Users want to pick a sample point and the
parameters they care about and get a dedicated dashboard in Grafana with a
shareable link.

## Requirements (from brainstorming)

- **Generation unit:** the user selects **one sample point + a set of
  parameters**; one dashboard is generated containing only the panels for that
  selection (uid derived from the selection so re-generating overwrites).
- **UI location:** a "Lab Dashboard generator" section on the **Monitoring &
  Analytics** page (`Grafana.tsx`), next to the existing report-template
  generator. Pick a point, multi-select parameters, click Generate, get an
  "Open in Grafana" link.
- **Panel layout:** one **time-series panel per selected parameter** (with the
  parameter's min/max limits drawn as threshold lines), plus one **latest-values
  table** panel covering the whole selection. Mirrors the `lab-quality.json`
  style.
- **Reuse** the existing Grafana write flow (build dashboard JSON → `POST
  /api/dashboards/db` with `overwrite: true`, authenticated via `render_auth()`
  + `render_headers()`).
- **Security:** `point_code` / `param_code` are embedded as SQL string literals
  in each panel's `rawSql`. Because operators can add catalog entries via the
  inline "+ new" flow, codes are not fully trusted — escape single quotes
  (`'` → `''`) and validate codes against an allowlist (`[A-Za-z0-9_-]+`).

## Architecture

### Backend — builder (`app/services/grafana_templates.py`)

Add two pure functions (no I/O), unit-testable:

```
def lab_dashboard_uid(point_id: int, parameter_ids: list[int]) -> str
    # deterministic: "sr-lab-{point_id}-{h}" where h = short stable hash of
    # sorted(parameter_ids) (e.g. first 8 hex chars of a sha1 of the joined ids).
    # Same point + same parameter set => same uid => Grafana overwrite.

def build_lab_dashboard(
    *,
    point_id: int,
    point_code: str,
    point_name: str,
    params: list[LabParamSpec],   # ordered as selected; each: id, code, name, unit, min_limit, max_limit
) -> dict
    # returns a Grafana dashboard JSON dict:
    #   uid = lab_dashboard_uid(point_id, [p.id for p in params])
    #   title = f"Lab — {point_name}"
    #   tags = ["lab", "generated"]
    #   datasource = {"type": "postgres", "uid": "timescaledb"} on every target
    #   time = {"from": "now-30d", "to": "now"}
    #   panels:
    #     - one timeseries panel per param, gridPos stacked vertically (w=24,h=8),
    #       rawSql:
    #         SELECT time AS "time", param_code AS metric, value
    #         FROM v_lab_timeseries
    #         WHERE point_code = '<esc point_code>' AND param_code = '<esc p.code>'
    #               AND $__timeFilter(time)
    #         ORDER BY time
    #       fieldConfig.defaults.thresholds: limit lines from p.min_limit/p.max_limit
    #         (mode "absolute", steps for set limits; thresholds style = line via
    #          custom.thresholdsStyle = {"mode": "line"}). Unit from p.unit.
    #     - one table panel at the bottom (w=24,h=10):
    #         SELECT time, param_name, value, unit, min_limit, max_limit
    #         FROM v_lab_timeseries
    #         WHERE point_code = '<esc>' AND param_code IN ('<esc>', '<esc>', ...)
    #               AND $__timeFilter(time)
    #         ORDER BY time DESC LIMIT 200
```

`LabParamSpec` is a small dataclass/TypedDict local to the service (id, code,
name, unit, min_limit, max_limit). A private `_sql_str(value: str) -> str`
helper validates against `^[A-Za-z0-9_-]+$` (raising `ValueError` on violation)
and escapes single quotes, returning a quoted SQL literal. Codes that fail the
allowlist raise `ValueError`, surfaced by the endpoint as HTTP 422.

### Backend — endpoint (`app/api/grafana_dashboards.py`)

```
class LabDashboardGenerateIn(BaseModel):
    sample_point_id: int
    parameter_ids: list[int] = Field(min_length=1, max_length=50)
    # validator: unique, positive

@router.post("/dashboards/from-lab")
async def generate_from_lab(body, db, user=get_current_user, _feature=require_feature("grafana")):
    # 1. load LabSamplePoint by id → 404 "Numune noktası bulunamadı" if missing
    # 2. load LabParameter rows where id in parameter_ids → 404 {"missing_parameter_ids": [...]}
    #    for any not found; preserve the request's parameter order
    # 3. build params: list[LabParamSpec] from the rows
    # 4. dashboard = build_lab_dashboard(point_id=..., point_code=..., point_name=..., params=...)
    #       (a ValueError from code-allowlist → 422 with the message)
    # 5. POST to Grafana /api/dashboards/db (httpx.AsyncClient, base_url=GRAFANA_URL,
    #       auth=render_auth(), headers=render_headers(), timeout=10, transport=_transport)
    #       body {"dashboard": dashboard, "overwrite": True}
    #       httpx.HTTPError → 502 "Grafana erişilemedi"; status>=400 → 502 "...yazılamadı: HTTP {code}"
    # 6. return {"uid": lab_dashboard_uid(point_id, parameter_ids),
    #            "title": f"Lab — {point.name}",
    #            "url": payload.get("url") or f"/d/{uid}",
    #            "status": payload.get("status", "success")}
```

Guard: `require_feature("grafana")` + `get_current_user` — same as the
report-template generator. Reuse the module's existing `_transport` (test
monkeypatch seam), `render_auth`, `render_headers`, `settings.GRAFANA_URL`.
Imports added: `LabSamplePoint`, `LabParameter` from `app.models.lab`, and the
two new builder functions.

### Frontend — Monitoring & Analytics page (`src/pages/Grafana.tsx`)

Add a "Lab Dashboard" generator card/section below the existing report-template
generator form:

- On mount, load `listLabSamplePoints({approved: true})` and
  `listLabParameters({approved: true})` (the hand-written axios client functions
  already exist).
- A sample-point `<select>` and a parameter multi-select (`<select multiple>`,
  same pattern the existing Grafana generator uses for tags).
- A "Generate Dashboard" button → `generateLabDashboard({ sample_point_id,
  parameter_ids })` (new client function). Disabled until a point and ≥1
  parameter are chosen.
- On success, show an "Open in Grafana" link built from the returned `url`
  (reuse the page's existing `buildGrafanaPath`/`GRAFANA_URL` helper), plus a
  success state; on error, an inline error line.
- All strings via i18n (`grafana` namespace), 5 languages (en/tr/ru/de/ar).

New client function in `src/api/client.ts` (hand-written axios style):
`generateLabDashboard(data) => api.post('/grafana/dashboards/from-lab', data)`.

### Data flow

```
Grafana.tsx (point + params)
   → POST /api/grafana/dashboards/from-lab
       → load point + params from DB
       → build_lab_dashboard(...)  (panels query v_lab_timeseries)
       → POST Grafana /api/dashboards/db (overwrite)
   → {uid, url} → "Open in Grafana" link
```

## Testing (TDD; existing patterns)

- **Builder unit (`tests/test_lab_grafana_builder.py` or extend an existing
  grafana-templates test):**
  - `lab_dashboard_uid` is deterministic and order-independent in the parameter
    list (sorted before hashing).
  - `build_lab_dashboard` produces one timeseries panel per param + one table
    panel; every target's datasource uid is `timescaledb`; each panel's `rawSql`
    references `v_lab_timeseries` with the correct `point_code`/`param_code`;
    min/max limits appear as threshold steps when set, absent when null.
  - Single-quote escaping: a `point_code`/`param_code` containing a disallowed
    character raises `ValueError`; a valid code round-trips. (Allowlist makes a
    `'` impossible, so the test asserts the allowlist rejects it.)
- **Endpoint (`tests/test_lab_grafana_api.py`, mirror
  `test_grafana_report_dashboard_api.py` — `httpx.MockTransport` via the module
  `_transport` seam + `require_feature` override):**
  - 404 when the sample point is missing.
  - 422 when `parameter_ids` is empty (Pydantic) and 404
    `{"missing_parameter_ids": [...]}` when a parameter id doesn't exist.
  - Success path: returns `uid` = `sr-lab-{point_id}-{hash}`, a `url`, status
    `success`; the captured Grafana request body has `overwrite: true` and a
    dashboard with the expected panel count.
  - Grafana failure (mock returns 500) → 502.
- **Frontend (`vitest`):** a pure helper if one is extracted (e.g.
  `canGenerateLab(pointId, paramIds)`), plus `tsc -b` + `pnpm lint` green.

## Out of scope (YAGNI)

- Deleting generated dashboards from the app.
- Auto-generating one dashboard per sample point (only the explicit selection).
- Mirrored parameters already appear on SCADA dashboards / Advanced Reports —
  not re-addressed here.
- Grafana template variables in the generated dashboard (each panel targets a
  fixed parameter; the existing `lab-quality.json` covers the variable-driven
  exploration case).

## Notes / limitations

- The generated dashboard's panels query `v_lab_timeseries` through the
  **Postgres/TimescaleDB** datasource (uid `timescaledb`). In SQLite dev the
  view exists for tests, but live Grafana rendering needs the Postgres
  deployment — same caveat as `lab-quality.json`.
- The Grafana renderer/instance must be reachable at `settings.GRAFANA_URL` with
  `render_auth()`/`render_headers()` credentials (service-account token or
  basic-auth) — identical to the report-template generator.
