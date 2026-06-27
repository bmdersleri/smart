# Delete Grafana Dashboards — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan
**Builds on:** the Monitoring & Analytics page (`Grafana.tsx`) dashboard list and the dashboard-generation endpoints in `app/api/grafana_dashboards.py`.

## Problem

The app generates Grafana dashboards (report-template and lab generators write
dashboards with `sr-*` uids) and lists all dashboards on the Monitoring &
Analytics page, but there is no way to delete a dashboard from the app — they
accumulate and can only be removed from Grafana directly.

## Requirements (from brainstorming)

- **Scope:** ANY dashboard shown in the Monitoring & Analytics list is
  deletable (not only app-generated ones). Grafana itself refuses to delete
  file-provisioned dashboards, which is a natural safety net surfaced as an
  error.
- **Permission:** delete is admin-only. The backend requires `admin` +
  writable; the frontend shows the delete control only to admins.
- **Confirmation:** deletion is destructive → a confirmation step before the
  call.
- **Security:** the `uid` reaches a Grafana API path, so it must be validated
  against the Grafana uid allowlist (`^[A-Za-z0-9_-]+$`) to prevent path
  traversal / SSRF.

## Architecture

### Backend — endpoint (`app/api/grafana_dashboards.py`)

```
@router.delete("/dashboards/{uid}")
async def delete_dashboard(uid, db?, user=require_role("admin"), _writable=require_writable, _feature=require_feature("grafana")):
    # 1. validate uid against ^[A-Za-z0-9_-]+$  -> 422 "Geçersiz dashboard uid" on violation
    #    (the uid is interpolated into the Grafana URL path, so this is the SSRF/traversal guard)
    # 2. DELETE Grafana /api/dashboards/uid/{uid} via
    #    httpx.AsyncClient(base_url=settings.GRAFANA_URL, auth=render_auth(),
    #                      headers=render_headers(), timeout=10.0, transport=_transport)
    # 3. response mapping:
    #    - 200             -> {"uid": uid, "status": "deleted"}
    #    - 404             -> HTTP 404 "Dashboard bulunamadı"
    #    - 400 or 412      -> HTTP 409 "Dashboard silinemez (provisioned olabilir)"
    #      (Grafana returns 400/412 with "Dashboard cannot be deleted because it is provisioned")
    #    - other >= 400    -> HTTP 502 "Grafana dashboard silinemedi: HTTP {code}"
    #    - httpx.HTTPError  -> HTTP 502 "Grafana erişilemedi: {e}"
```

Guards: `require_feature("grafana")` + `require_role("admin")` + `require_writable`
(matches the project's destructive-mutation convention: admin role, blocked in
demo read-only mode). Reuses the module's existing `_transport` test seam,
`render_auth`, `render_headers`, `settings.GRAFANA_URL`. A small private helper
`_valid_grafana_uid(uid: str) -> bool` (compiled `^[A-Za-z0-9_-]+$`) is the
validation unit.

### Frontend — Monitoring & Analytics page (`src/pages/Grafana.tsx`)

- A small delete control (trash icon / "Sil" button) on each dashboard tab in
  the existing dashboard list, rendered ONLY when the current user is an admin
  (`useAuth().user.role === 'admin'` — confirm how the page reads auth; the app
  has an `AuthContext` with `user.role`).
- Click → a confirmation step (a `window.confirm` with the dashboard title is
  sufficient for this internal tool) → `deleteGrafanaDashboard(uid)`.
- On success: reload the dashboard list (`loadDashboards()`); if the deleted
  dashboard was the active tab, clear/reset `activeUid` to the first remaining.
- On error: an inline error line (e.g. the 409 "silinemez (provisioned)"
  message), without removing the tab.
- A pure helper `canDeleteDashboard(role: string | undefined): boolean`
  (`role === 'admin'`) drives whether the control renders — unit-tested.

New client function in `src/api/client.ts` (hand-written axios style):
`deleteGrafanaDashboard(uid: string) => api.delete('/grafana/dashboards/{uid}')`.

i18n keys in the `grafana` namespace (all 5 languages): `delete`,
`confirm_delete` (a template with the title), `deleted`, `delete_error`.

### Data flow

```
Grafana.tsx tab [Sil] (admin only)
   → window.confirm(title)
   → DELETE /api/grafana/dashboards/{uid}
       → validate uid → Grafana DELETE /api/dashboards/uid/{uid}
   → success: loadDashboards() + fix activeUid
   → error: inline message (404 / 409 provisioned / 502)
```

## Testing (TDD; existing patterns)

- **Backend (`tests/test_grafana_delete_api.py`, mirror
  `test_grafana_report_dashboard_api.py` — `_auth_override` fixture +
  `monkeypatch` on the module `_transport`):**
  - Success: Grafana mock returns 200 for `DELETE /api/dashboards/uid/<uid>` →
    endpoint returns 200 `{uid, status:"deleted"}`; the captured request path +
    method are asserted.
  - Grafana 404 → endpoint 404.
  - Grafana 412 (provisioned) → endpoint 409.
  - Invalid uid (e.g. `"../foo"` or `"a/b"`) → 422, and NO Grafana call is made.
  - Non-admin user → 403 (override `get_current_user` with an operator; the
    `require_role("admin")` guard is NOT overridden so it actually runs — note
    the `_auth_override` fixture must be adjusted to test the role gate, or a
    separate operator fixture used).
  - Transport error → 502.
- **Frontend (`vitest`):** `canDeleteDashboard('admin') === true`,
  `canDeleteDashboard('operator') === false`, `canDeleteDashboard(undefined) ===
  false`; plus `pnpm tsc -b` + `pnpm lint` green.

## Out of scope (YAGNI)

- Bulk delete / multi-select.
- Trash / undo / restore.
- Force-deleting provisioned dashboards (Grafana blocks this by design).
- A custom confirmation modal (the native `window.confirm` is sufficient for an
  internal admin tool; can be upgraded later).

## Notes / limitations

- File-provisioned dashboards (e.g. `lab-quality`, `scada-metrics`) cannot be
  deleted — Grafana rejects it and the app surfaces a 409. This is intended.
- The Grafana instance must be reachable at `settings.GRAFANA_URL` with
  `render_auth()`/`render_headers()` credentials — identical to the generators.
