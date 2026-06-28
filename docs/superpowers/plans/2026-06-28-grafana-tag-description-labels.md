# Grafana Tag-Description Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated Grafana panels (charts + tables) label series/rows with the tag's `description` (falling back to `name`), and an admin endpoint bulk-updates already-generated managed dashboards.

**Architecture:** A single shared SQL label expression `_TAG_LABEL` is used by all dashboard generators in `app/services/grafana_templates.py`. A pure `apply_tag_label(sql)` transform rewrites the exact label substrings that older generators emitted, used by a new admin endpoint `POST /api/grafana/dashboards/refresh-managed` that fetches each managed dashboard from Grafana, transforms its panel SQL in place, and writes it back with `overwrite:true`.

**Tech Stack:** Python 3.14, FastAPI, httpx (Grafana HTTP, `httpx.MockTransport` in tests), pytest-asyncio, frser-sqlite + PostgreSQL SQL strings.

## Global Constraints

- Label expression, verbatim: `COALESCE(NULLIF(t.description, ''), t.name)`
- Table column header alias, verbatim: `AS "Etiket"`
- Lab dashboards (`_lab_timeseries_panel`, `build_lab_dashboard`) MUST NOT change — they use `param_name`, not `t.name`.
- `GROUP BY t.name` / `ORDER BY t.name` in breach SQL stay on `t.name` (grouping must remain per-tag even when two tags share a description).
- Grafana HTTP in the endpoint follows the existing pattern in `app/api/grafana_dashboards.py`: `httpx.AsyncClient(base_url=settings.GRAFANA_URL, auth=render_auth(), headers=render_headers(), timeout=10.0, transport=_transport)`.
- Admin + writable + feature gating, verbatim deps: `Depends(require_role("admin"))`, `Depends(require_writable)`, `Depends(require_feature("grafana"))`.
- Python only; `python` not `python3`. Run tests with `just test` or `pytest`.

---

### Task 1: Shared label expression + frser generators (water_quality, facility_overview)

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py` (add `_TAG_LABEL`; update `build_water_quality_dashboard` lines ~308-332 and `build_facility_overview_dashboard` lines ~211-217)
- Test: `scada-reporter/backend/tests/test_grafana_templates.py`

**Interfaces:**
- Produces: module constant `_TAG_LABEL: str = "COALESCE(NULLIF(t.description, ''), t.name)"` (used by Tasks 2 and 3).
- Produces: `build_water_quality_dashboard` / `build_facility_overview_dashboard` output whose trend `metric` column and table label columns use `_TAG_LABEL`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_grafana_templates.py`:

```python
from app.services.grafana_templates import (
    build_water_quality_dashboard,
    build_facility_overview_dashboard,
)

_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def _all_sql(dash: dict) -> str:
    return " ".join(
        t.get("rawQueryText", "") + " " + t.get("queryText", "")
        for p in dash["panels"]
        for t in p.get("targets", [])
    )


def test_water_quality_uses_description_label():
    dash = build_water_quality_dashboard("sr-wq-x", "WQ", [1, 2])
    sql = _all_sql(dash)
    # trend series label
    assert f"{_LABEL} AS metric" in sql
    # latest-values table: inner label + outer readable header
    assert f"{_LABEL} AS name" in sql
    assert 'name AS "Etiket"' in sql
    # breach table header
    assert f'{_LABEL} AS "Etiket"' in sql
    # grouping stays per-tag
    assert "GROUP BY t.name" in sql
    # no bare technical-name label remains
    assert "t.name AS metric" not in sql


def test_facility_overview_uses_description_label():
    dash = build_facility_overview_dashboard("sr-fac-x", "FAC")
    sql = _all_sql(dash)
    assert f"{_LABEL} AS name" in sql
    assert 'name AS "Etiket"' in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_templates.py::test_water_quality_uses_description_label tests/test_grafana_templates.py::test_facility_overview_uses_description_label -v`
Expected: FAIL (assertions on `_LABEL` not found; current SQL uses `t.name AS metric`).

- [ ] **Step 3: Write minimal implementation**

In `grafana_templates.py`, add the constant near the top (after imports, before `TEMPLATES`):

```python
# Tag'in görünen etiketi: açıklama varsa onu, boşsa teknik ada düş.
_TAG_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"
```

Replace `build_water_quality_dashboard`'s three SQL blocks:

```python
    trend_sql = (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        f"{_TAG_LABEL} AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND tr.tag_id IN ({ids}) "
        "ORDER BY time"
    )
    latest_sql = (
        'SELECT name AS "Etiket", value, unit, quality, timestamp FROM ('
        f"SELECT t.id AS tid, {_TAG_LABEL} AS name, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE t.id IN ({ids})"
        ") WHERE rn = 1 ORDER BY tid"
    )
    breach_sql = (
        f'SELECT {_TAG_LABEL} AS "Etiket", '
        "sum(CASE WHEN t.min_alarm IS NOT NULL "
        'AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS "Alt Limit", '
        "sum(CASE WHEN t.max_alarm IS NOT NULL "
        'AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS "Üst Limit" '
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND t.id IN ({ids}) "
        "GROUP BY t.name ORDER BY t.name"
    )
```

Replace `build_facility_overview_dashboard`'s `last_values_sql`:

```python
    last_values_sql = (
        'SELECT name AS "Etiket", device, value, unit, quality, timestamp FROM ('
        f"SELECT {_TAG_LABEL} AS name, t.device, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id"
        ") WHERE rn = 1 ORDER BY timestamp DESC LIMIT 20"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_templates.py -v`
Expected: PASS (new tests + existing template tests still green).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_templates.py
git commit -m "feat(grafana): label frser panels with tag description"
```

---

### Task 2: PostgreSQL report-template generator

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py` (`build_report_template_dashboard` lines ~564, ~583, ~601-608)
- Test: `scada-reporter/backend/tests/test_grafana_report_dashboard.py`

**Interfaces:**
- Consumes: `_TAG_LABEL` from Task 1.
- Produces: `build_report_template_dashboard` output whose trend `metric` and table labels use `_TAG_LABEL`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_grafana_report_dashboard.py`:

```python
from app.services.grafana_templates import build_report_template_dashboard

_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def test_report_template_uses_description_label():
    dash = build_report_template_dashboard(
        template_id=7,
        title="R",
        tag_ids=[1, 2],
        time_range_type="last_24h",
        show_trend_charts=True,
        show_summary_stats=True,
        anomaly_enabled=True,
        show_anomaly_table=True,
    )
    sql = " ".join(
        t.get("rawQueryText", "") + " " + t.get("queryText", "")
        for p in dash["panels"]
        for t in p.get("targets", [])
    )
    assert f"{_LABEL} AS metric" in sql
    assert f'SELECT DISTINCT ON (t.id) {_LABEL} AS "Etiket"' in sql
    assert f'{_LABEL} AS "Etiket"' in sql  # breach
    assert "t.name AS metric" not in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_report_dashboard.py::test_report_template_uses_description_label -v`
Expected: FAIL (current SQL uses `t.name AS metric` / `DISTINCT ON (t.id) t.name`).

- [ ] **Step 3: Write minimal implementation**

In `build_report_template_dashboard`, replace the three inline SQL strings:

Trend:
```python
                    "SELECT $__time(tr.timestamp) AS time, "
                    f"{_TAG_LABEL} AS metric, tr.value AS value "
                    "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
                    f"WHERE $__timeFilter(tr.timestamp) AND tr.tag_id IN ({ids}) ORDER BY 1"
```

Son Değerler:
```python
                    f'SELECT DISTINCT ON (t.id) {_TAG_LABEL} AS "Etiket", '
                    "tr.value, t.unit, tr.quality, tr.timestamp "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE t.id IN ({ids}) ORDER BY t.id, tr.timestamp DESC"
```

Limit Aşımı Özeti:
```python
                    f'SELECT {_TAG_LABEL} AS "Etiket", '
                    "sum(CASE WHEN t.min_alarm IS NOT NULL "
                    'AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS "Alt Limit", '
                    "sum(CASE WHEN t.max_alarm IS NOT NULL "
                    'AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS "Üst Limit" '
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE $__timeFilter(tr.timestamp) AND t.id IN ({ids}) "
                    "GROUP BY t.name ORDER BY t.name"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_report_dashboard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_report_dashboard.py
git commit -m "feat(grafana): label report-template panels with tag description"
```

---

### Task 3: `apply_tag_label` transform for existing dashboards

**Files:**
- Modify: `scada-reporter/backend/app/services/grafana_templates.py` (add `apply_tag_label`)
- Test: Create `scada-reporter/backend/tests/test_grafana_apply_tag_label.py`

**Interfaces:**
- Consumes: `_TAG_LABEL`.
- Produces: `def apply_tag_label(sql: str) -> str` — pure, idempotent. Used by Task 4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grafana_apply_tag_label.py`:

```python
from app.services.grafana_templates import apply_tag_label

_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def test_trend_metric_swapped():
    old = "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"
    assert f"{_LABEL} AS metric" in apply_tag_label(old)
    assert "t.name AS metric" not in apply_tag_label(old)


def test_breach_header_swapped():
    old = 'SELECT t.name, sum(CASE WHEN t.min_alarm IS NOT NULL THEN 1 ELSE 0 END) AS "Alt Limit"'
    out = apply_tag_label(old)
    assert f'SELECT {_LABEL} AS "Etiket", sum(CASE' in out


def test_distinct_on_table_swapped():
    old = "SELECT DISTINCT ON (t.id) t.name, tr.value, t.unit FROM tags t"
    out = apply_tag_label(old)
    assert f'SELECT DISTINCT ON (t.id) {_LABEL} AS "Etiket", tr.value' in out


def test_subquery_table_swapped():
    old = (
        "SELECT name, value, unit, quality, timestamp FROM ("
        "SELECT t.id AS tid, t.name, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id WHERE t.id IN (1)"
        ") WHERE rn = 1 ORDER BY tid"
    )
    out = apply_tag_label(old)
    assert f"{_LABEL} AS name" in out
    assert 'SELECT name AS "Etiket", value' in out


def test_facility_subquery_table_swapped():
    old = (
        "SELECT name, device, value, unit, quality, timestamp FROM ("
        "SELECT t.name, t.device, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id"
        ") WHERE rn = 1 ORDER BY timestamp DESC LIMIT 20"
    )
    out = apply_tag_label(old)
    assert f"SELECT {_LABEL} AS name, t.device" in out
    assert 'SELECT name AS "Etiket", device' in out


def test_idempotent():
    old = "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"
    once = apply_tag_label(old)
    assert apply_tag_label(once) == once


def test_lab_param_name_untouched():
    old = "SELECT CAST(strftime('%s', time) AS INTEGER) AS time, param_name AS metric, value"
    assert apply_tag_label(old) == old


def test_unrelated_sql_untouched():
    old = "SELECT count(*) AS \"Tag\" FROM tags"
    assert apply_tag_label(old) == old
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_apply_tag_label.py -v`
Expected: FAIL with "cannot import name 'apply_tag_label'".

- [ ] **Step 3: Write minimal implementation**

Add to `grafana_templates.py`:

```python
# (old emitted substring, new substring) — exact, order matters. More specific
# patterns first so prefixes (e.g. breach "SELECT t.name, sum") are not shadowed
# by the generic subquery "SELECT t.name, t.device" replacement.
_LABEL_SWAPS: tuple[tuple[str, str], ...] = (
    ("t.name AS metric", f"{_TAG_LABEL} AS metric"),
    (
        "SELECT DISTINCT ON (t.id) t.name,",
        f'SELECT DISTINCT ON (t.id) {_TAG_LABEL} AS "Etiket",',
    ),
    ("SELECT t.name, sum(CASE", f'SELECT {_TAG_LABEL} AS "Etiket", sum(CASE'),
    # subquery tables: inner label first, then outer readable header
    ("SELECT t.id AS tid, t.name,", f"SELECT t.id AS tid, {_TAG_LABEL} AS name,"),
    ("SELECT t.name, t.device,", f"SELECT {_TAG_LABEL} AS name, t.device,"),
    ("SELECT name, value, unit, quality, timestamp FROM (",
     'SELECT name AS "Etiket", value, unit, quality, timestamp FROM ('),
    ("SELECT name, device, value, unit, quality, timestamp FROM (",
     'SELECT name AS "Etiket", device, value, unit, quality, timestamp FROM ('),
)


def apply_tag_label(sql: str) -> str:
    """Rewrite the technical-name label substrings older generators emitted to
    use _TAG_LABEL. Pure + idempotent: if the SQL already references the label
    expression, or contains no known pattern, it is returned unchanged."""
    if "COALESCE(NULLIF(t.description" in sql:
        return sql
    out = sql
    for old, new in _LABEL_SWAPS:
        out = out.replace(old, new)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_apply_tag_label.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/grafana_templates.py scada-reporter/backend/tests/test_grafana_apply_tag_label.py
git commit -m "feat(grafana): add apply_tag_label transform for existing dashboards"
```

---

### Task 4: `refresh-managed` admin endpoint

**Files:**
- Modify: `scada-reporter/backend/app/api/grafana_dashboards.py` (add endpoint; import `apply_tag_label`)
- Test: Create `scada-reporter/backend/tests/test_grafana_refresh_managed.py`

**Interfaces:**
- Consumes: `apply_tag_label` (Task 3); existing `render_auth`, `render_headers`, `_transport`, `settings.GRAFANA_URL`.
- Produces: `POST /api/grafana/dashboards/refresh-managed` → `{"updated": int, "skipped": list[dict]}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grafana_refresh_managed.py`:

```python
import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _override(role: str):
    fake = User(id=1, username="u", email="u@x.io", hashed_password=hash_password("x"), role=role)
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[require_feature("grafana")] = lambda: None


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_feature("grafana"), None)


def _handler(search_rows, dash_by_uid, posted):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/search":
            return httpx.Response(200, json=search_rows)
        if path.startswith("/api/dashboards/uid/"):
            uid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"dashboard": dash_by_uid[uid]})
        if path == "/api/dashboards/db":
            body = request.read().decode()
            posted.append(body)
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)
    return handler


@pytest.mark.asyncio
async def test_refresh_updates_managed(client, monkeypatch):
    _override("admin")
    search_rows = [{"uid": "sr-wq-1"}, {"uid": "sr-lab-2-aa"}]
    dash_by_uid = {
        "sr-wq-1": {"uid": "sr-wq-1", "panels": [
            {"targets": [{"rawQueryText": "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr",
                          "queryText": "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"}]}
        ]},
        "sr-lab-2-aa": {"uid": "sr-lab-2-aa", "panels": [
            {"targets": [{"rawQueryText": "SELECT time, param_name AS metric, value",
                          "queryText": "SELECT time, param_name AS metric, value"}]}
        ]},
    }
    posted: list[str] = []
    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(_handler(search_rows, dash_by_uid, posted)), raising=False)

    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["updated"] == 1                       # only sr-wq-1 changed
    assert any(s["uid"] == "sr-lab-2-aa" for s in data["skipped"])  # lab = no-op
    assert len(posted) == 1
    assert "COALESCE(NULLIF(t.description" in posted[0]


@pytest.mark.asyncio
async def test_refresh_non_admin_403(client, monkeypatch):
    _override("operator")
    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport",
                        httpx.MockTransport(lambda req: httpx.Response(200, json=[])), raising=False)
    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_grafana_down_502(client, monkeypatch):
    _override("admin")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    import app.api.grafana_dashboards as gd
    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_refresh_managed.py -v`
Expected: FAIL (404 — endpoint not defined).

- [ ] **Step 3: Write minimal implementation**

In `grafana_dashboards.py`, add `apply_tag_label` to the `grafana_templates` import list, then add:

```python
@router.post("/dashboards/refresh-managed")
async def refresh_managed_dashboards(
    user: User = Depends(require_role("admin")),
    _writable=Depends(require_writable),
    _feature=Depends(require_feature("grafana")),
) -> dict:
    """Re-label all managed (sr-*) dashboards with the tag-description label,
    in place. Idempotent: dashboards already using the label are skipped."""
    updated = 0
    skipped: list[dict] = []
    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=render_auth(),
            headers=render_headers(),
            timeout=15.0,
            transport=_transport,
        ) as http:
            search = await http.get("/api/search", params={"type": "dash-db"})
            if search.status_code >= 400:
                raise HTTPException(
                    status_code=502, detail=f"Grafana arama hatası: HTTP {search.status_code}"
                )
            for row in search.json():
                uid = row.get("uid", "")
                if not uid.startswith("sr-") or not _valid_grafana_uid(uid):
                    continue
                try:
                    got = await http.get(f"/api/dashboards/uid/{uid}")
                    if got.status_code >= 400:
                        skipped.append({"uid": uid, "reason": f"fetch HTTP {got.status_code}"})
                        continue
                    dashboard = got.json().get("dashboard") or {}
                    changed = False
                    for panel in dashboard.get("panels", []):
                        for target in panel.get("targets", []):
                            for key in ("rawQueryText", "queryText"):
                                sql = target.get(key)
                                if isinstance(sql, str):
                                    new_sql = apply_tag_label(sql)
                                    if new_sql != sql:
                                        target[key] = new_sql
                                        changed = True
                    if not changed:
                        skipped.append({"uid": uid, "reason": "no-op"})
                        continue
                    posted = await http.post(
                        "/api/dashboards/db",
                        json={"dashboard": dashboard, "overwrite": True},
                    )
                    if posted.status_code >= 400:
                        skipped.append({"uid": uid, "reason": f"write HTTP {posted.status_code}"})
                        continue
                    updated += 1
                except httpx.HTTPError as e:
                    skipped.append({"uid": uid, "reason": f"error: {e}"})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    return {"updated": updated, "skipped": skipped}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && python -m pytest tests/test_grafana_refresh_managed.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/grafana_dashboards.py scada-reporter/backend/tests/test_grafana_refresh_managed.py
git commit -m "feat(grafana): add refresh-managed endpoint to re-label existing dashboards"
```

---

### Task 5: Frontend admin button + regenerate client + docs

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Grafana.tsx` (admin-only button calling the endpoint)
- Modify: `scada-reporter/backend/CLAUDE.md` *(project root — note the description-label behavior)* — if a frontend client wrapper exists, regenerate via `just gen-client`; otherwise call with a direct authenticated `apiClient`/fetch following the page's existing API usage.
- Test: manual (Playwright) — covered by verification, no new unit test.

**Interfaces:**
- Consumes: `POST /api/grafana/dashboards/refresh-managed` (Task 4).

- [ ] **Step 1: Add the button + handler**

In `Grafana.tsx`, near the existing header actions (where `open_grafana` link lives ~line 221), add an admin-only button. Use the page's existing auth/role source (`AuthContext`) and the generated client if `just gen-client` exposes the new route, else a direct `fetch('/api/...')` with the Bearer token like other authed calls in the codebase:

```tsx
{user?.role === 'admin' && (
  <button
    onClick={handleRefreshManaged}
    disabled={refreshing}
    className="px-3 py-1.5 text-sm rounded-lg bg-surface-sunken hover:bg-surface-sunken/80 border border-edge text-gray-300 disabled:opacity-50"
  >
    {refreshing ? t('refresh_managed_busy') : t('refresh_managed')}
  </button>
)}
```

Handler (state `refreshing`, `refreshResult`):

```tsx
const handleRefreshManaged = async () => {
  setRefreshing(true)
  try {
    const r = await refreshManagedDashboards()   // generated client; or fetch wrapper
    setRefreshResult(`${r.data.updated} güncellendi, ${r.data.skipped.length} atlandı`)
    loadDashboards()
  } catch (e) {
    setRefreshResult(e instanceof Error ? e.message : String(e))
  } finally {
    setRefreshing(false)
  }
}
```

Add i18n keys `refresh_managed` / `refresh_managed_busy` to all 5 locale `grafana.json` files (en/tr/ru/de/ar), e.g. tr: `"refresh_managed": "Panoları güncelle"`, `"refresh_managed_busy": "Güncelleniyor…"`.

- [ ] **Step 2: Regenerate the API client (if used)**

Run (backend must be running): `cd scada-reporter && just gen-client`
Expected: `refreshManagedDashboards` (or equivalent) appears in `frontend/src/api/generated`.

- [ ] **Step 3: Typecheck**

Run: `cd scada-reporter/frontend && pnpm exec tsc --noEmit`
Expected: no output (clean).

- [ ] **Step 4: Manual verification (Playwright/browser)**

Log in as admin, open İzleme & Analitik, click "Panoları güncelle". Confirm it returns a summary and existing dashboards now show descriptions in legends/tables. Confirm a non-admin user does not see the button.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src scada-reporter/backend/CLAUDE.md
git commit -m "feat(grafana): admin button to re-label existing dashboards + docs"
```

---

## Self-Review

- **Spec coverage:** label format COALESCE (Tasks 1-3); scope charts+tables+report-template, lab excluded (Tasks 1,2 + lab untouched constant; Task 3 `test_lab_param_name_untouched`); `AS "Etiket"` header (Tasks 1-3); auto bulk update Approach A (Tasks 3,4); error handling 502 + per-dashboard skip (Task 4 tests); idempotency (Task 3 `test_idempotent`, Task 4 no-op skip). Frontend button optional → Task 5.
- **Placeholder scan:** none — all SQL/code/tests are concrete.
- **Type consistency:** `apply_tag_label(sql: str) -> str` defined Task 3, consumed Task 4; `_TAG_LABEL` defined Task 1, consumed Tasks 2-3; endpoint return `{"updated": int, "skipped": list[dict]}` matches Task 4 test assertions.
- **Note for implementer:** Task 5's exact client call depends on whether `just gen-client` is run; the page already does a bare `fetch('/grafana-api/...')` for search and uses the generated client for templates — follow whichever the route ends up exposed through. If the generated client is not regenerated, use an authenticated `fetch('/api/grafana/dashboards/refresh-managed', { method:'POST', headers:{ Authorization: \`Bearer ${token}\` } })`.
