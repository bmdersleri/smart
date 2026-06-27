# Generate Grafana Dashboards from Lab Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pick a lab sample point + parameters on the Monitoring & Analytics page and generate a dedicated Grafana dashboard (one time-series panel per parameter with limit lines + a latest-values table) written to Grafana.

**Architecture:** A pure builder in `grafana_templates.py` produces the dashboard JSON (reusing the existing `_timeseries_panel`/`_table_panel`/`_base_dashboard` helpers, querying `v_lab_timeseries`). A new endpoint `POST /grafana/dashboards/from-lab` in `grafana_dashboards.py` validates the selection against the `lab_*` tables and writes the dashboard to Grafana via the existing `_transport`/`render_auth`/`render_headers` flow. A generator section on `Grafana.tsx` drives it.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy async / pytest-asyncio + httpx.MockTransport; React 19 / TypeScript / hand-written axios client / i18next; Grafana HTTP API (`/api/dashboards/db`).

## Global Constraints

- Python baseline **3.14** (never lower).
- Backend tests: `just test` (pytest async, `-n auto`, randomized). TDD per-file: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v` from the backend dir (`scada-reporter/backend`). Python is `python` (not `python3`); venv `.venv/Scripts/python`.
- Lint/type gate `just check` (ruff + mypy + frontend) before each task's final commit.
- Endpoint guard: `require_feature("grafana")` + `get_current_user` (same as the report-template generator).
- Grafana write: `httpx.AsyncClient(base_url=settings.GRAFANA_URL, auth=render_auth(), headers=render_headers(), timeout=10.0, transport=_transport)` → `POST /api/dashboards/db` with `{"dashboard": ..., "overwrite": True}`. `httpx.HTTPError` → 502; `response.status_code >= 400` → 502.
- Every panel target datasource is `{"type": "postgres", "uid": "timescaledb"}`; panels query the `v_lab_timeseries` view (columns: `time, point_code, param_code, param_name, unit, value, min_limit, max_limit`).
- SQL safety: `point_code`/`param_code` go into `rawSql` as quoted literals — validate each against `^[A-Za-z0-9_-]+$` (raise `ValueError` on violation; the endpoint maps that to HTTP 422). The allowlist forbids quotes, so no injection is possible.
- uid is deterministic: `sr-lab-{point_id}-{8-hex hash of sorted unique parameter_ids}` → re-generating the same selection overwrites the same dashboard.
- Frontend: NO `prettier --write` (compact style). i18n strings in the `grafana` namespace, all 5 languages (en/tr/ru/de/ar). Client is hand-written axios (`api.get`/`api.post`, read `.data`).
- Branch: `master`, commit directly (dev-phase, no PR). Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Drift hazard:** background automation intermittently switches the working-tree branch and may leave a polluted git index. Implementers MUST: `git checkout master` at start and re-verify before commit; stage with an EXPLICIT pathspec on `git commit` (e.g. `git commit -- <file1> <file2>`) — never `git add -A`/`git add .` and never a bare `git commit` that trusts the index.

---

## File Structure

- `app/services/grafana_templates.py` — ADD `LabParamSpec` dataclass, `_lab_sql_code()` helper, `lab_dashboard_uid()`, `_lab_timeseries_panel()`, `build_lab_dashboard()`. (Reuses existing `_timeseries_panel`, `_table_panel`, `_base_dashboard`.)
- `app/api/grafana_dashboards.py` — ADD `LabDashboardGenerateIn` model + `POST /dashboards/from-lab` endpoint.
- `tests/test_lab_grafana_builder.py` — builder unit tests.
- `tests/test_lab_grafana_api.py` — endpoint tests (httpx.MockTransport).
- `scada-reporter/frontend/src/api/client.ts` — ADD `generateLabDashboard`.
- `scada-reporter/frontend/src/pages/Grafana.tsx` — ADD the Lab Dashboard generator section.
- `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/grafana.json` — ADD keys.

---

## Task 1: Backend builder (`build_lab_dashboard` + uid + SQL guard)

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py`
- Test: `scada-reporter/backend/tests/test_lab_grafana_builder.py`

**Interfaces:**
- Consumes: existing `_timeseries_panel(panel_id, title, raw_sql, *, x, y, w, h, unit)`, `_table_panel(panel_id, title, raw_sql, *, x, y, w, h)`, `_base_dashboard(uid, title, tags, panels)` in the same module.
- Produces:
  - `@dataclass LabParamSpec: id: int; code: str; name: str; unit: str; min_limit: float | None; max_limit: float | None`
  - `lab_dashboard_uid(point_id: int, parameter_ids: list[int]) -> str`
  - `build_lab_dashboard(*, point_id: int, point_code: str, point_name: str, params: list[LabParamSpec]) -> dict`
  - (raises `ValueError` when any `point_code`/`param_code` fails the allowlist, or when `params` is empty)

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_grafana_builder.py`:

```python
import pytest

from app.services.grafana_templates import (
    LabParamSpec,
    build_lab_dashboard,
    lab_dashboard_uid,
)


def _params():
    return [
        LabParamSpec(id=10, code="PH", name="pH", unit="", min_limit=6.5, max_limit=9.0),
        LabParamSpec(id=20, code="COD", name="COD", unit="mg/L", min_limit=None, max_limit=400.0),
    ]


def test_uid_is_deterministic_and_order_independent():
    a = lab_dashboard_uid(5, [20, 10])
    b = lab_dashboard_uid(5, [10, 20])
    assert a == b
    assert a.startswith("sr-lab-5-")
    # different point or param set -> different uid
    assert lab_dashboard_uid(6, [10, 20]) != a
    assert lab_dashboard_uid(5, [10]) != a


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
    # every target uses the timescaledb postgres datasource and queries the view
    for panel in dash["panels"]:
        assert panel["datasource"] == {"type": "postgres", "uid": "timescaledb"}
        sql = panel["targets"][0]["rawSql"]
        assert "v_lab_timeseries" in sql
    # the pH panel filters by its own codes
    ph = next(p for p in dash["panels"] if p["title"].startswith("pH"))
    ph_sql = ph["targets"][0]["rawSql"]
    assert "point_code = 'INLET'" in ph_sql
    assert "param_code = 'PH'" in ph_sql


def test_limits_become_threshold_lines():
    dash = build_lab_dashboard(
        point_id=5, point_code="INLET", point_name="Inlet", params=_params()
    )
    ph = next(p for p in dash["panels"] if p["title"].startswith("pH"))
    steps = ph["fieldConfig"]["defaults"]["thresholds"]["steps"]
    values = [s["value"] for s in steps]
    assert 6.5 in values and 9.0 in values
    assert ph["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] == {"mode": "line"}
    # COD has only a max limit -> only that line (plus the base None step)
    cod = next(p for p in dash["panels"] if p["title"].startswith("COD"))
    cod_values = [s["value"] for s in cod["fieldConfig"]["defaults"]["thresholds"]["steps"]]
    assert 400.0 in cod_values
    assert 6.5 not in cod_values


def test_bad_code_raises():
    with pytest.raises(ValueError):
        build_lab_dashboard(
            point_id=1,
            point_code="IN'LET",  # quote -> allowlist violation
            point_name="x",
            params=_params(),
        )


def test_empty_params_raises():
    with pytest.raises(ValueError):
        build_lab_dashboard(point_id=1, point_code="INLET", point_name="x", params=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_builder.py -p no:randomly -n0 -v`
Expected: FAIL — `ImportError` (`LabParamSpec`/`build_lab_dashboard`/`lab_dashboard_uid` not defined).

- [ ] **Step 3: Implement the builder**

In `scada-reporter/backend/app/services/grafana_templates.py`, add near the top imports:

```python
import hashlib
import re
from dataclasses import dataclass
```

Then add these definitions (place them after the existing `_table_panel`/`_base_dashboard` helpers so the reused helpers are defined above):

```python
_LAB_CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _lab_sql_code(value: str) -> str:
    """Return *value* as a safe single-quoted SQL literal.

    Codes come from the lab catalog, where operators can add entries, so they
    are validated against a strict allowlist (letters, digits, '_' and '-').
    The allowlist forbids quotes, so no SQL injection is possible.
    """
    if not _LAB_CODE_RE.match(value or ""):
        raise ValueError(f"Geçersiz kod (yalnız harf/rakam/_/- izinli): {value!r}")
    return f"'{value}'"


@dataclass
class LabParamSpec:
    id: int
    code: str
    name: str
    unit: str
    min_limit: float | None
    max_limit: float | None


def lab_dashboard_uid(point_id: int, parameter_ids: list[int]) -> str:
    ids = ",".join(str(i) for i in sorted({int(i) for i in parameter_ids}))
    digest = hashlib.sha1(ids.encode("utf-8")).hexdigest()[:8]  # noqa: S324 (not security)
    return f"sr-lab-{int(point_id)}-{digest}"


def _lab_timeseries_panel(
    panel_id: int, point_code: str, param: LabParamSpec, *, y: int
) -> dict:
    """A v_lab_timeseries time-series panel for one parameter, with min/max limit lines."""
    raw_sql = (
        f"SELECT time AS \"time\", param_code AS metric, value "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code = {_lab_sql_code(param.code)} "
        f"AND $__timeFilter(time) ORDER BY time"
    )
    title = f"{param.name}{f' ({param.unit})' if param.unit else ''}"
    panel = _timeseries_panel(
        panel_id, title, raw_sql, x=0, y=y, w=24, h=8, unit=param.unit or "short"
    )
    steps: list[dict] = [{"color": "green", "value": None}]
    if param.min_limit is not None:
        steps.append({"color": "orange", "value": param.min_limit})
    if param.max_limit is not None:
        steps.append({"color": "red", "value": param.max_limit})
    # Grafana wants steps sorted ascending; the base None step stays first.
    steps[1:] = sorted(steps[1:], key=lambda s: s["value"])
    panel["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": steps}
    panel["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] = {"mode": "line"}
    return panel


def build_lab_dashboard(
    *, point_id: int, point_code: str, point_name: str, params: list[LabParamSpec]
) -> dict:
    if not params:
        raise ValueError("Dashboard için en az bir parametre seçilmeli")
    panels: list[dict] = []
    y = 0
    for idx, param in enumerate(params, start=1):
        panels.append(_lab_timeseries_panel(idx, point_code, param, y=y))
        y += 8
    # latest-values table across the whole selection
    codes_in = ", ".join(_lab_sql_code(p.code) for p in params)
    table_sql = (
        f"SELECT time, param_name, value, unit, min_limit, max_limit "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code IN ({codes_in}) "
        f"AND $__timeFilter(time) ORDER BY time DESC LIMIT 200"
    )
    panels.append(
        _table_panel(len(params) + 1, "Son değerler", table_sql, x=0, y=y, w=24, h=10)
    )
    uid = lab_dashboard_uid(point_id, [p.id for p in params])
    return _base_dashboard(uid, f"Lab — {point_name}", ["lab"], panels)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_builder.py -p no:randomly -n0 -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + commit**

Run: `.venv/Scripts/python -m ruff check app/services/grafana_templates.py` → clean.

```bash
git checkout master
git commit -- scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_lab_grafana_builder.py -m "feat(lab-grafana): dashboard builder + uid + SQL code allowlist

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(If pre-commit reformats, re-run the same `git commit --` with the same paths.)

---

## Task 2: Backend endpoint (`POST /grafana/dashboards/from-lab`)

**Files:**
- Modify: `scada-reporter/backend/app/api/grafana_dashboards.py`
- Test: `scada-reporter/backend/tests/test_lab_grafana_api.py`

**Interfaces:**
- Consumes: Task 1 `LabParamSpec`, `build_lab_dashboard`, `lab_dashboard_uid`; existing module-level `_transport`, `render_auth`, `render_headers`, `settings`, `get_current_user`, `require_feature`, `get_db`; models `LabSamplePoint`, `LabParameter` from `app.models.lab`.
- Produces: `POST /api/grafana/dashboards/from-lab` returning `{uid, title, url, status}`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_grafana_api.py`:

```python
import json

import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.lab import LabParameter, LabSamplePoint
from app.models.user import User


@pytest.fixture
def _auth_override():
    fake = User(id=1, username="a", email="a@x.io", hashed_password=hash_password("x"), role="admin")
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[guard] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(guard, None)


async def _seed(db):
    point = LabSamplePoint(code="INLET", name="Inlet")
    ph = LabParameter(code="PH", name="pH", min_limit=6.5, max_limit=9.0)
    cod = LabParameter(code="COD", name="COD", unit="mg/L", max_limit=400.0)
    db.add_all([point, ph, cod])
    await db.commit()
    await db.refresh(point)
    await db.refresh(ph)
    await db.refresh(cod)
    return point, ph, cod


@pytest.mark.asyncio
async def test_generate_from_lab_success(client, db_session, monkeypatch, _auth_override):
    point, ph, cod = await _seed(db_session)
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/db":
            posted["json"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "success", "url": "/d/x/lab"})
        return httpx.Response(404)

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id, cod.id]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uid"].startswith(f"sr-lab-{point.id}-")
    assert body["title"] == "Lab — Inlet"
    assert posted["json"]["overwrite"] is True
    assert len(posted["json"]["dashboard"]["panels"]) == 3  # 2 ts + 1 table


@pytest.mark.asyncio
async def test_missing_point_404(client, db_session, monkeypatch, _auth_override):
    _, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False)
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": 99999, "parameter_ids": [ph.id]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_empty_params_422(client, db_session, monkeypatch, _auth_override):
    point, _, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False)
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_missing_parameter_404(client, db_session, monkeypatch, _auth_override):
    point, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False)
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id, 88888]},
    )
    assert r.status_code == 404
    assert "missing_parameter_ids" in str(r.json()["detail"])


@pytest.mark.asyncio
async def test_grafana_failure_502(client, db_session, monkeypatch, _auth_override):
    point, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(500)), raising=False
    )
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id]},
    )
    assert r.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_api.py -p no:randomly -n0 -v`
Expected: FAIL — 404/405 (endpoint not mounted).

- [ ] **Step 3: Implement the endpoint**

In `scada-reporter/backend/app/api/grafana_dashboards.py`, extend the imports:

```python
from app.models.lab import LabParameter, LabSamplePoint
from app.services.grafana_templates import (
    build_dashboard,
    build_lab_dashboard,
    build_report_template_dashboard,
    dashboard_uid,
    get_template,
    lab_dashboard_uid,
    list_templates,
    report_dashboard_uid,
    LabParamSpec,
)
```
(Merge with the existing `from app.services.grafana_templates import (...)` block rather than duplicating it; add `Field` is already imported from pydantic.)

Add the request model near `DashboardGenerateIn`:

```python
class LabDashboardGenerateIn(BaseModel):
    sample_point_id: int
    parameter_ids: list[int] = Field(min_length=1, max_length=50)

    @field_validator("parameter_ids")
    @classmethod
    def _unique_positive(cls, v: list[int]) -> list[int]:
        out = [int(i) for i in v if int(i) > 0]
        if not out:
            raise ValueError("en az bir parametre seçin")
        # preserve order, drop duplicates
        seen: set[int] = set()
        result = []
        for i in out:
            if i not in seen:
                seen.add(i)
                result.append(i)
        return result
```

Add the endpoint (after `generate_from_report_template`):

```python
@router.post("/dashboards/from-lab")
async def generate_from_lab(
    body: LabDashboardGenerateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
) -> dict:
    point = await db.get(LabSamplePoint, body.sample_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Numune noktası bulunamadı")

    rows = (
        (await db.execute(select(LabParameter).where(LabParameter.id.in_(body.parameter_ids))))
        .scalars()
        .all()
    )
    by_id = {p.id: p for p in rows}
    missing = [pid for pid in body.parameter_ids if pid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail={"missing_parameter_ids": missing})

    # preserve the request's parameter order
    params = [
        LabParamSpec(
            id=p.id,
            code=p.code,
            name=p.name,
            unit=p.unit,
            min_limit=p.min_limit,
            max_limit=p.max_limit,
        )
        for p in (by_id[pid] for pid in body.parameter_ids)
    ]

    try:
        dashboard = build_lab_dashboard(
            point_id=point.id,
            point_code=point.code,
            point_name=point.name,
            params=params,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=render_auth(),
            headers=render_headers(),
            timeout=10.0,
            transport=_transport,
        ) as http:
            response = await http.post(
                "/api/dashboards/db",
                json={"dashboard": dashboard, "overwrite": True},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Grafana dashboard yazılamadı: HTTP {response.status_code}"
        )

    payload = response.json()
    uid = lab_dashboard_uid(point.id, body.parameter_ids)
    return {
        "uid": uid,
        "title": f"Lab — {point.name}",
        "url": payload.get("url") or f"/d/{uid}",
        "status": payload.get("status", "success"),
    }
```

> NOTE: `select`, `BaseModel`, `Field`, `field_validator`, `httpx`, `HTTPException`, `Depends`, `AsyncSession`, `get_db`, `get_current_user`, `require_feature`, `settings`, `render_auth`, `render_headers`, `User`, `_transport` are already imported/defined in this module (the existing generators use them). Only add what is missing (`LabSamplePoint`, `LabParameter`, the three new `grafana_templates` names).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_api.py -p no:randomly -n0 -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Full lab + grafana suite + checks**

Run: `.venv/Scripts/python -m pytest tests/test_lab_grafana_api.py tests/test_lab_grafana_builder.py tests/test_grafana_report_dashboard_api.py -n0 -v` then `just check`
Expected: all pass; ruff + mypy clean.

- [ ] **Step 6: Commit**

```bash
git checkout master
git commit -- scada-reporter/backend/app/api/grafana_dashboards.py scada-reporter/backend/tests/test_lab_grafana_api.py -m "feat(lab-grafana): POST /grafana/dashboards/from-lab endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Frontend generator on Monitoring & Analytics

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Modify: `scada-reporter/frontend/src/pages/Grafana.tsx`
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/grafana.json`
- Test: `scada-reporter/frontend/src/pages/labDashboard.helper.test.ts`

**Interfaces:**
- Consumes: existing hand-written axios helpers `listLabSamplePoints`, `listLabParameters` (from the Lab feature) and the `Grafana.tsx` `GRAFANA_URL`/`buildGrafanaPath` helpers.
- Produces: `generateLabDashboard(data: { sample_point_id: number; parameter_ids: number[] })` and a pure `canGenerateLab(pointId, paramIds)` helper.

- [ ] **Step 1: Add the client function**

In `scada-reporter/frontend/src/api/client.ts`, add alongside the other hand-written lab functions (follow the existing axios style — `api.post`, returns the `AxiosResponse`):

```ts
export const generateLabDashboard = (data: { sample_point_id: number; parameter_ids: number[] }) =>
  api.post<{ uid: string; title: string; url: string; status: string }>(
    '/grafana/dashboards/from-lab',
    data,
  )
```

- [ ] **Step 2: Write the failing test (pure helper)**

Create `scada-reporter/frontend/src/pages/labDashboard.helper.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { canGenerateLab } from './labDashboard.helper'

describe('canGenerateLab', () => {
  it('false when no point', () => {
    expect(canGenerateLab('', [1])).toBe(false)
  })
  it('false when no parameters', () => {
    expect(canGenerateLab('5', [])).toBe(false)
  })
  it('true when point and at least one parameter', () => {
    expect(canGenerateLab('5', [1, 2])).toBe(true)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/labDashboard.helper.test.ts`
Expected: FAIL — cannot resolve `./labDashboard.helper`.

- [ ] **Step 4: Implement the helper**

Create `scada-reporter/frontend/src/pages/labDashboard.helper.ts`:

```ts
// A lab dashboard can be generated once a sample point and >=1 parameter are chosen.
export function canGenerateLab(pointId: number | '' | string, paramIds: number[]): boolean {
  return pointId !== '' && pointId !== undefined && paramIds.length > 0
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm vitest run src/pages/labDashboard.helper.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 6: Add i18n keys (all 5 languages)**

In each `src/i18n/locales/{en,tr,ru,de,ar}/grafana.json`, add the same keys (English values shown; translate per language):

```json
{
  "lab_gen_title": "Lab Dashboard",
  "lab_gen_subtitle": "Generate a Grafana dashboard from lab data",
  "lab_gen_point": "Sample Point",
  "lab_gen_params": "Parameters",
  "lab_gen_button": "Generate Dashboard",
  "lab_gen_generating": "Generating…",
  "lab_gen_open": "Open in Grafana"
}
```
Turkish values: `"Lab Dashboard"`, `"Lab verisinden Grafana panosu üret"`, `"Numune Noktası"`, `"Parametreler"`, `"Dashboard Oluştur"`, `"Oluşturuluyor…"`, `"Grafana'da Aç"`. Provide ru/de/ar with the same key set.

- [ ] **Step 7: Add the generator section to Grafana.tsx**

In `scada-reporter/frontend/src/pages/Grafana.tsx`:
1. Add imports: `generateLabDashboard`, `listLabParameters`, `listLabSamplePoints`, the lab types (`LabParameterOut`, `LabSamplePointOut`) from `'../api/client'`, and `canGenerateLab` from `'./labDashboard.helper'`.
2. Add state: `labPoints`, `labParams` (loaded on mount via `Promise.all([listLabSamplePoints({approved:true}), listLabParameters({approved:true})])`, reading `.data`), `labPointId` (number|''), `labParamIds` (number[]), `labGenerating` (bool), `labResult` ({url}|null), `labError` (string|null).
3. Render a card (match the existing report-template generator card styling on this page) with: a sample-point `<select>`, a parameter `<select multiple>` (options from `labParams`, value = `labParamIds.map(String)`, onChange maps selectedOptions to numbers — mirror the existing tag multi-select in this page), a "Generate Dashboard" button disabled unless `canGenerateLab(labPointId, labParamIds)` and not `labGenerating`, and on success an "Open in Grafana" link built with the page's `buildGrafanaPath(labResult.url, theme)` (or the existing URL helper), plus an inline error line for `labError`.
4. The submit handler calls `generateLabDashboard({ sample_point_id: Number(labPointId), parameter_ids: labParamIds })`, sets `labResult` from `res.data`, handles errors into `labError`, toggles `labGenerating`.

All visible strings use `t('lab_gen_*')` from the `grafana` namespace (the page already uses `useTranslation('grafana')`). Keep the compact code style; do not run prettier.

- [ ] **Step 8: Verify**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/labDashboard.helper.test.ts` (3 pass), `pnpm tsc -b` (0 errors), `pnpm lint` (clean).

- [ ] **Step 9: Commit**

```bash
git checkout master
git commit -- scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/Grafana.tsx scada-reporter/frontend/src/pages/labDashboard.helper.ts scada-reporter/frontend/src/pages/labDashboard.helper.test.ts scada-reporter/frontend/src/i18n/locales/en/grafana.json scada-reporter/frontend/src/i18n/locales/tr/grafana.json scada-reporter/frontend/src/i18n/locales/ru/grafana.json scada-reporter/frontend/src/i18n/locales/de/grafana.json scada-reporter/frontend/src/i18n/locales/ar/grafana.json -m "feat(lab-grafana): generate lab dashboard section on Monitoring & Analytics

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: End-to-end verification + docs

**Files:**
- Modify: `docs/lab-data-entry.md` (add a "Generate Grafana dashboard" subsection)

- [ ] **Step 1: Full backend suite**

Run (from `scada-reporter/backend`): `just test`
Expected: all pass including the new `test_lab_grafana_builder.py` (5) and `test_lab_grafana_api.py` (5).

- [ ] **Step 2: All checks**

Run (from repo root): `just check`
Expected: ruff + mypy + frontend lint/build green. (A pre-existing, non-lab bandit B608 warning set may remain — out of scope.)

- [ ] **Step 3: Manual E2E (browser)** — requires the backend restarted to load the new endpoint (NSSM `EkontBackend` restart needs elevation), the frontend, and Grafana with a Postgres/TimescaleDB datasource.
1. Monitoring & Analytics → Lab Dashboard section: pick a sample point, select 2 parameters, Generate.
2. Confirm the success state + "Open in Grafana" link; open it and verify the dashboard has one time-series panel per parameter (limit lines visible for parameters with limits) + a latest-values table.
3. Re-generating the same selection overwrites (same uid) rather than duplicating.
Note in the doc: live panels need the Postgres/TimescaleDB datasource (SQLite dev only builds the view for tests).

- [ ] **Step 4: Doc + commit**

Add a "Generate a Grafana dashboard from a selection" subsection to `docs/lab-data-entry.md` (sample point + parameters → dashboard, uid `sr-lab-{point}-{hash}`, overwrite-on-regenerate, Postgres requirement).

```bash
git checkout master
git commit -- docs/lab-data-entry.md -m "docs(lab-grafana): document the lab dashboard generator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master
```

---

## Self-Review

**Spec coverage:**
- Generation unit = point + selected parameters → Task 2 endpoint + Task 1 builder. ✓
- UI on Monitoring & Analytics (`Grafana.tsx`) → Task 3. ✓
- One time-series panel per parameter with limit lines + latest table → Task 1 (`_lab_timeseries_panel` thresholds + `_table_panel`) + `test_limits_become_threshold_lines`. ✓
- Reuse Grafana write flow (`_transport`/`render_auth`/`render_headers`, overwrite) → Task 2. ✓
- SQL safety (allowlist + quoting) → Task 1 `_lab_sql_code` + `test_bad_code_raises`. ✓
- Deterministic uid `sr-lab-{point_id}-{hash}` → Task 1 `lab_dashboard_uid` + test. ✓
- Guard `require_feature("grafana")` + `get_current_user` → Task 2. ✓
- i18n 5 languages → Task 3 step 6. ✓
- Postgres datasource caveat → Task 4 doc. ✓

**Placeholder scan:** No "TBD"/"implement later". Task 3 step 7 describes the Grafana.tsx wiring in prose rather than a full file rewrite — deliberate: the page is large and the implementer must match its existing card/multi-select pattern (read it first); the testable logic (`canGenerateLab`, `generateLabDashboard`) is fully specified with code.

**Type consistency:** `LabParamSpec(id, code, name, unit, min_limit, max_limit)` defined in Task 1, consumed identically in Task 2. `build_lab_dashboard(*, point_id, point_code, point_name, params)` and `lab_dashboard_uid(point_id, parameter_ids)` signatures match across Tasks 1–2. `generateLabDashboard({sample_point_id, parameter_ids})` matches the endpoint body `LabDashboardGenerateIn`. `canGenerateLab(pointId, paramIds)` matches its test.
