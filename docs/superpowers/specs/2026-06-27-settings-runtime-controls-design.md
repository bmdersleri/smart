# Settings Runtime Controls — Design Spec

**Date:** 2026-06-27
**Status:** Proposed
**Scope:** Add admin-only runtime controls to the Settings page for collector and scheduler processes that run inside the current backend API process. This does not add full backend start/stop because a stopped backend cannot receive the matching start request.

## 1. Goal

Provide operators with a safe Settings-page control surface for runtime components:

- Show backend liveness, readiness-relevant runtime state, uptime, and process start time.
- Show whether collector and scheduler are configured and currently running.
- Allow admins to start or stop the in-process collector.
- Allow admins to start or stop the in-process scheduler.
- Keep the backend API process alive while these controls are used.

## 2. Non-Goals

- Do not stop the backend API process from its own API.
- Do not start the backend API process from the frontend.
- Do not manage Windows services, NSSM, systemd, Docker, or external supervisors in this task.
- Do not change the supported API/collector/scheduler production topology.
- Do not expose runtime controls to non-admin users.

## 3. Rationale

The Settings page can call the backend only while the backend is running. A full backend stop button would make the corresponding start action unreachable unless a separate supervisor API exists. The safe first step is therefore to keep FastAPI alive and control only the long-running in-process tasks that are already started from lifespan:

- S7 poller
- OPC UA server
- PLC monitor
- APScheduler

This matches the current development topology and keeps production role separation intact.

## 4. Current Architecture

Relevant current files:

- `scada-reporter/backend/app/main.py` starts database init, scheduler, collector, OPC UA, and monitor tasks during lifespan.
- `scada-reporter/backend/app/services/scheduler.py` owns the global APScheduler instance.
- `scada-reporter/backend/app/collector/poller.py` provides `poll_loop`.
- `scada-reporter/backend/app/collector/opcua_server.py` provides `opcua_server.start()` and `opcua_server.stop()`.
- `scada-reporter/backend/app/monitor/monitor.py` provides `plc_monitor_loop`.
- `scada-reporter/frontend/src/pages/Settings.tsx` renders admin-only settings cards.
- `scada-reporter/frontend/src/api/client.ts` is the handwritten API adapter used by Settings.

## 5. Backend Design

Add a small runtime-control service that owns task references outside `main.lifespan`.

Recommended module:

```text
scada-reporter/backend/app/services/runtime_control.py
```

Responsibilities:

- Track collector task state.
- Start collector tasks idempotently.
- Stop collector tasks idempotently.
- Start scheduler idempotently.
- Stop scheduler idempotently.
- Return a serializable status payload.
- Reuse existing collector and scheduler functions.

Collector control should manage the same task group as lifespan:

- `poll_loop()`
- `opcua_server.start()`
- `plc_monitor_loop()`

Scheduler control should use:

- `start_scheduler(settings.DATABASE_URL)`
- `get_scheduler().shutdown(wait=False)`

Add an admin-only router:

```text
scada-reporter/backend/app/api/runtime.py
```

Suggested endpoints:

```http
GET  /api/runtime/status
POST /api/runtime/collector/start
POST /api/runtime/collector/stop
POST /api/runtime/scheduler/start
POST /api/runtime/scheduler/stop
```

Authorization:

- Require `require_role("admin")`.

Expected response shape:

```json
{
  "controls_enabled": true,
  "collector": {
    "configured": true,
    "running": true,
    "poller_running": true,
    "opcua_running": true,
    "monitor_running": true
  },
  "scheduler": {
    "configured": true,
    "running": true
  },
  "backend": {
    "status": "ok",
    "uptime_seconds": 123.4,
    "started_at": "2026-06-27T..."
  }
}
```

## 6. Frontend Design

Add an admin-only Settings card:

```text
Runtime Controls
```

Content:

- Backend status and uptime.
- Collector status with a start/stop toggle.
- Scheduler status with a start/stop toggle.
- Mutating controls disabled while a request is in flight.
- Error message shown inline if an action fails.

Behavior:

- Fetch status when the card mounts.
- Refresh status after every start/stop action.
- Optionally poll status every few seconds.
- Hide the card from non-admin users.

The card should be a separate component, for example:

```text
scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx
```

## 7. Safety Rules

- Runtime controls must be admin-only.
- Stop actions must not stop FastAPI itself.
- Start actions must be idempotent.
- Stop actions must be idempotent.
- Production deployments that use split API/collector/scheduler processes should continue using process managers as the source of truth.
- The UI should label the controls as in-process runtime controls, not full backend service controls.

## 8. Verification

Backend:

- Unit tests for runtime status shape.
- Unit tests that start/stop collector are idempotent with mocked tasks.
- Unit tests that scheduler start/stop call the existing scheduler service correctly.
- Existing scheduler lifespan tests remain green.

Frontend:

- Settings card renders only for admin.
- Start/stop buttons call the expected API functions.
- Errors render without crashing the page.
- TypeScript compile passes.

Full checks:

```powershell
just check
```

Targeted checks:

```powershell
cd scada-reporter/backend && .venv/Scripts/pytest tests/test_runtime_control.py tests/test_scheduler_lifespan.py -q
cd scada-reporter/frontend && pnpm test -- Settings
```

## 9. Merge Criteria

- Implementation is on a feature branch.
- User-unrelated dirty files are not committed.
- Runtime controls work without stopping the API.
- Targeted backend and frontend tests pass.
- Branch is merged only after successful verification.
