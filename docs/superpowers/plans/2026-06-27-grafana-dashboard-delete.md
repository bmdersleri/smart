# Delete Grafana Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin delete any Grafana dashboard from the Monitoring & Analytics page, via a backend endpoint that proxies the Grafana delete API with a uid allowlist guard.

**Architecture:** A new `DELETE /grafana/dashboards/{uid}` endpoint in `grafana_dashboards.py` (admin-only, uid validated against the Grafana charset) calls Grafana `DELETE /api/dashboards/uid/{uid}` via the existing `_transport`/`render_auth`/`render_headers` flow and maps statuses (404→404, provisioned 400/412→409, other→502). The Monitoring & Analytics page (`Grafana.tsx`) adds an admin-only delete control per dashboard tab with a confirm step that reloads the list on success.

**Tech Stack:** Python 3.14 / FastAPI / pytest-asyncio + httpx.MockTransport; React 19 / TypeScript / hand-written axios client / i18next; Grafana HTTP API (`DELETE /api/dashboards/uid/{uid}`).

## Global Constraints

- Python baseline **3.14**. Backend tests TDD per-file: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v` (from `scada-reporter/backend`; Python is `python`, venv `.venv/Scripts/python`).
- Lint/type gate `just check` (ruff + mypy + frontend) before each task's final commit.
- Endpoint guards: `require_feature("grafana")` + `require_role("admin")` + `require_writable` (destructive-mutation convention).
- Grafana call: `httpx.AsyncClient(base_url=settings.GRAFANA_URL, auth=render_auth(), headers=render_headers(), timeout=10.0, transport=_transport)`. `httpx.HTTPError` → 502.
- **Security:** the `uid` path param is interpolated into the Grafana URL path → validate against `^[A-Za-z0-9_-]+$` (raise 422 on violation) BEFORE any Grafana call. This is the traversal/SSRF guard.
- Status mapping: Grafana 200 → `{"uid": uid, "status": "deleted"}`; Grafana 404 → HTTP 404; Grafana 400 or 412 → HTTP 409 (provisioned); other ≥400 → HTTP 502.
- Frontend: NO `prettier --write` (compact style). i18n strings in the `grafana` namespace, all 5 languages (en/tr/ru/de/ar). Client is hand-written axios (`api.delete`, etc.).
- Delete control on each dashboard tab is rendered ONLY for admins (`user.role === 'admin'`). `Grafana.tsx` currently imports `useSettings` (not auth) — the frontend task must add `import { useAuth } from '../context/AuthContext'` and `const { user } = useAuth()`.
- Branch: `master`, commit directly (dev-phase, no PR). Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Drift hazard:** background automation intermittently switches the working-tree branch + pollutes the git index. Implementers MUST: `git checkout master` at start and re-verify before commit; commit with an EXPLICIT pathspec `git commit -- <files>` (never `git add -A`/bare `git commit`).

---

## File Structure

- `app/api/grafana_dashboards.py` — ADD `_valid_grafana_uid()` helper + `DELETE /dashboards/{uid}` endpoint.
- `tests/test_grafana_delete_api.py` — endpoint tests (httpx.MockTransport).
- `scada-reporter/frontend/src/api/client.ts` — ADD `deleteGrafanaDashboard`.
- `scada-reporter/frontend/src/pages/Grafana.tsx` — ADD admin-only per-tab delete control + handler.
- `scada-reporter/frontend/src/pages/grafanaDelete.helper.ts` (+ `.test.ts`) — pure `canDeleteDashboard`.
- `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/grafana.json` — ADD keys.

---

## Task 1: Backend `DELETE /grafana/dashboards/{uid}` endpoint

**Files:**
- Modify: `scada-reporter/backend/app/api/grafana_dashboards.py`
- Test: `scada-reporter/backend/tests/test_grafana_delete_api.py`

**Interfaces:**
- Consumes: existing module-level `_transport`, `render_auth`, `render_headers`, `settings`, `require_feature`, `require_writable`, `httpx`, `HTTPException`, `Depends`, `User`; and `require_role` from `app.api.auth` (the report-template generators use `get_current_user`/`require_feature`; `require_role` and `require_writable` may need importing — check the existing imports and add only what's missing).
- Produces: `DELETE /api/grafana/dashboards/{uid}` returning `{uid, status}`; private `_valid_grafana_uid(uid: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_grafana_delete_api.py`:

```python
import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _override(role: str):
    fake = User(
        id=1, username="u", email="u@x.io", hashed_password=hash_password("x"), role=role
    )
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[guard] = lambda: None


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_feature("grafana"), None)


@pytest.mark.asyncio
async def test_admin_deletes_dashboard(client, monkeypatch):
    _override("admin")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"message": "Dashboard deleted"})

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.delete("/api/grafana/dashboards/sr-lab-5-abc123de")
    assert r.status_code == 200, r.text
    assert r.json() == {"uid": "sr-lab-5-abc123de", "status": "deleted"}
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/dashboards/uid/sr-lab-5-abc123de"


@pytest.mark.asyncio
async def test_invalid_uid_422_no_grafana_call(client, monkeypatch):
    _override("admin")
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    # a/b would traverse the Grafana path; %2e etc. also rejected by the allowlist
    r = await client.delete("/api/grafana/dashboards/a..b")
    assert r.status_code == 422
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_grafana_404(client, monkeypatch):
    _override("admin")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/missinguid")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_provisioned_409(client, monkeypatch):
    _override("admin")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(412)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/labquality")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_403(client, monkeypatch):
    _override("operator")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(200)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/sr-rpt-1")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_transport_error_502(client, monkeypatch):
    _override("admin")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.delete("/api/grafana/dashboards/sr-rpt-1")
    assert r.status_code == 502
```

> NOTE on the 403 test: `require_role("admin")` runs as a real dependency (it is NOT overridden — only `get_current_user` and the `require_feature` guard are). With an operator user injected, `require_role("admin")` raises 403 before the endpoint body. This is the intended path.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_delete_api.py -p no:randomly -n0 -v`
Expected: FAIL — 404/405 (endpoint not mounted).

- [ ] **Step 3: Implement the endpoint**

In `scada-reporter/backend/app/api/grafana_dashboards.py`:

1. Ensure imports include `re` (add `import re` near the top if absent) and the guards. The module already imports `require_feature` and `get_current_user`; ADD to the `from app.api.auth import ...` line whatever is missing — it needs `require_role`. ADD `from app.api.license_guard import require_writable` if `require_writable` is not already imported (the module imports `require_feature` from `license_guard`; extend that line: `from app.api.license_guard import require_feature, require_writable`).

2. Add the uid validator near the top of the module (after imports):

```python
_GRAFANA_UID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _valid_grafana_uid(uid: str) -> bool:
    return bool(_GRAFANA_UID_RE.match(uid or ""))
```

3. Add the endpoint (after the other dashboard endpoints):

```python
@router.delete("/dashboards/{uid}")
async def delete_dashboard(
    uid: str,
    user: User = Depends(require_role("admin")),
    _writable=Depends(require_writable),
    _feature=Depends(require_feature("grafana")),
) -> dict:
    if not _valid_grafana_uid(uid):
        raise HTTPException(status_code=422, detail="Geçersiz dashboard uid")

    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=render_auth(),
            headers=render_headers(),
            timeout=10.0,
            transport=_transport,
        ) as http:
            response = await http.delete(f"/api/dashboards/uid/{uid}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Dashboard bulunamadı")
    if response.status_code in (400, 412):
        raise HTTPException(
            status_code=409, detail="Dashboard silinemez (provisioned olabilir)"
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Grafana dashboard silinemedi: HTTP {response.status_code}"
        )
    return {"uid": uid, "status": "deleted"}
```

> NOTE: confirm whether `require_role` is exported by `app.api.auth` (the audit router uses `require_role("admin")`, so it is). Do not add a `db` dependency — this endpoint needs no DB.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_grafana_delete_api.py -p no:randomly -n0 -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Checks + commit**

Run: `.venv/Scripts/python -m ruff check app/api/grafana_dashboards.py` → clean. Then `just check` (ruff + mypy + frontend) — confirm no new failures trace to this file.

```bash
git checkout master
git commit -- scada-reporter/backend/app/api/grafana_dashboards.py scada-reporter/backend/tests/test_grafana_delete_api.py -m "feat(grafana): DELETE /grafana/dashboards/{uid} (admin, uid allowlist)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(If pre-commit reformats, re-run the same `git commit --` with the same paths.)

---

## Task 2: Frontend admin-only delete control

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Modify: `scada-reporter/frontend/src/pages/Grafana.tsx`
- Create: `scada-reporter/frontend/src/pages/grafanaDelete.helper.ts`
- Test: `scada-reporter/frontend/src/pages/grafanaDelete.helper.test.ts`
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/grafana.json`

**Interfaces:**
- Consumes: Task 1 endpoint `DELETE /api/grafana/dashboards/{uid}`; the page's existing `dashboards` state (`{uid,title,url}[]`), `loadDashboards()`, `activeUid`/`setActiveUid`; `useAuth` from `../context/AuthContext` (provides `user: { id, username, role, ... } | null`).
- Produces: `deleteGrafanaDashboard(uid: string)` and pure `canDeleteDashboard(role: string | undefined): boolean`.

- [ ] **Step 1: Add the client function**

In `scada-reporter/frontend/src/api/client.ts`, add near the other grafana functions (hand-written axios style — note path interpolation):

```ts
export const deleteGrafanaDashboard = (uid: string) =>
  api.delete<{ uid: string; status: string }>(`/grafana/dashboards/${encodeURIComponent(uid)}`)
```

- [ ] **Step 2: Write the failing test (pure helper)**

Create `scada-reporter/frontend/src/pages/grafanaDelete.helper.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { canDeleteDashboard } from './grafanaDelete.helper'

describe('canDeleteDashboard', () => {
  it('true for admin', () => {
    expect(canDeleteDashboard('admin')).toBe(true)
  })
  it('false for operator', () => {
    expect(canDeleteDashboard('operator')).toBe(false)
  })
  it('false for undefined', () => {
    expect(canDeleteDashboard(undefined)).toBe(false)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/grafanaDelete.helper.test.ts`
Expected: FAIL — cannot resolve `./grafanaDelete.helper`.

- [ ] **Step 4: Implement the helper**

Create `scada-reporter/frontend/src/pages/grafanaDelete.helper.ts`:

```ts
// Only admins may delete dashboards (destructive; backend also enforces admin).
export function canDeleteDashboard(role: string | undefined): boolean {
  return role === 'admin'
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm vitest run src/pages/grafanaDelete.helper.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 6: Add i18n keys (all 5 languages)**

In each `src/i18n/locales/{en,tr,ru,de,ar}/grafana.json`, add the same keys (English shown; translate per language):

```json
{
  "delete": "Delete",
  "confirm_delete": "Delete dashboard \"{{title}}\"?",
  "deleted": "Deleted",
  "delete_error": "Could not delete"
}
```
Turkish: `"Sil"`, `"\"{{title}}\" panosunu sil?"`, `"Silindi"`, `"Silinemedi"`. Provide ru/de/ar with the same key set. (i18next interpolates `{{title}}` when called as `t('confirm_delete', { title })`.)

- [ ] **Step 7: Wire the delete control into Grafana.tsx**

In `scada-reporter/frontend/src/pages/Grafana.tsx`:
1. Add `import { useAuth } from '../context/AuthContext'` and `import { deleteGrafanaDashboard } from '../api/client'` (merge into the existing client import block), and `import { canDeleteDashboard } from './grafanaDelete.helper'`.
2. In the component, add `const { user } = useAuth()` and a `const [deleteError, setDeleteError] = useState<string | null>(null)`.
3. Add a handler:

```tsx
const handleDelete = async (uid: string, title: string) => {
  if (!window.confirm(t('confirm_delete', { title }))) return
  setDeleteError(null)
  try {
    await deleteGrafanaDashboard(uid)
    setActiveUid((prev) => (prev === uid ? '' : prev))
    loadDashboards()
  } catch (e) {
    setDeleteError(e instanceof Error ? e.message : String(e))
  }
}
```

4. In the dashboard tab list (around line 375, `dashboards.map((dash) => (...))`), render the existing tab button, and — only when `canDeleteDashboard(user?.role)` — a small delete button next to it that stops propagation and calls `handleDelete(dash.uid, dash.title)`. Match the page's compact Tailwind button styling; e.g. wrap the existing `<button>` and a new `<button onClick={(e) => { e.stopPropagation(); handleDelete(dash.uid, dash.title) }} title={t('delete')} className="...">✕</button>` in a small flex container keyed by `dash.uid`. Render `deleteError` as an inline red line near the tab row (reuse the page's existing error-line styling).

All visible strings via `t('...')` from the `grafana` namespace (the page already uses `useTranslation('grafana')`). Keep compact style; do not run prettier.

- [ ] **Step 8: Verify**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/grafanaDelete.helper.test.ts` (3 pass), `pnpm tsc -b` (0 errors), `pnpm lint` (clean).

- [ ] **Step 9: Commit + push**

```bash
git checkout master
git commit -- scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/Grafana.tsx scada-reporter/frontend/src/pages/grafanaDelete.helper.ts scada-reporter/frontend/src/pages/grafanaDelete.helper.test.ts scada-reporter/frontend/src/i18n/locales/en/grafana.json scada-reporter/frontend/src/i18n/locales/tr/grafana.json scada-reporter/frontend/src/i18n/locales/ru/grafana.json scada-reporter/frontend/src/i18n/locales/de/grafana.json scada-reporter/frontend/src/i18n/locales/ar/grafana.json -m "feat(grafana): admin delete control per dashboard tab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin master
```

---

## Self-Review

**Spec coverage:**
- Any listed dashboard deletable (per-tab control) → Task 2 step 7. ✓
- Admin-only (backend `require_role("admin")` + `require_writable`; frontend `canDeleteDashboard`) → Task 1 + Task 2. ✓
- Confirmation step → Task 2 `window.confirm`. ✓
- uid allowlist (traversal/SSRF guard) → Task 1 `_valid_grafana_uid` + `test_invalid_uid_422_no_grafana_call`. ✓
- Status mapping (404→404, 400/412→409 provisioned, other→502, HTTPError→502) → Task 1 + tests. ✓
- Reload list + fix active on success → Task 2 `handleDelete`. ✓
- i18n 5 languages → Task 2 step 6. ✓

**Placeholder scan:** No "TBD"/"implement later". Task 2 step 7 describes the Grafana.tsx tab-row wiring in prose (the page is large and the implementer must match its existing tab/button markup) but gives the exact handler code, the exact control to add, and the gating helper; the testable logic (`canDeleteDashboard`, `deleteGrafanaDashboard`) is fully specified.

**Type consistency:** `deleteGrafanaDashboard(uid: string)` matches the Task 1 path param. `canDeleteDashboard(role: string | undefined)` matches its test and the `user?.role` call site. `_valid_grafana_uid(uid: str) -> bool` consistent. Status-mapping values (404/409/502) match the spec and the endpoint tests.
