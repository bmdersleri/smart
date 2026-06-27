# Settings Runtime Controls Implementation Plan

> **For agentic workers:** start with the listed CodeGraph preflight, keep file ownership narrow, and verify with targeted tests. This plan is based on `docs/superpowers/specs/2026-06-27-settings-runtime-controls-design.md`.

**Goal:** Add an admin-only Settings-page control card for in-process collector and scheduler runtime controls while keeping the backend API process alive.

**Branch:** `feature/runtime-controls-settings`

## Global Constraints

- Do not implement full backend process stop/start.
- Do not edit generated OpenAPI files manually.
- Do not expose runtime controls to non-admin users.
- Do not commit unrelated dirty files.
- Preserve current startup behavior when `RUN_COLLECTOR=True` or `RUN_SCHEDULER=True`.
- Keep backend task control idempotent.

---

## Task 1: Add Backend Runtime Control Service

**CodeGraph preflight:**

```powershell
codegraph explore "backend startup scheduler collector poller opcua monitor runtime start stop health settings page" --max-files 10
codegraph impact get_scheduler --depth 3 --json
```

**Files:**

- Add: `scada-reporter/backend/app/services/runtime_control.py`
- Modify: `scada-reporter/backend/app/main.py`
- Add/modify backend tests.

**Steps:**

- [ ] Move collector task ownership into a service object or module-level controller.
- [ ] Implement `start_collector()`.
- [ ] Implement `stop_collector()`.
- [ ] Implement `collector_status()`.
- [ ] Implement `start_scheduler_runtime()`.
- [ ] Implement `stop_scheduler_runtime()`.
- [ ] Implement `runtime_status()`.
- [ ] Update lifespan to call the runtime service instead of owning local collector task variables.
- [ ] Preserve graceful shutdown.

**Verification:**

- [ ] Runtime control tests pass.
- [ ] Scheduler lifespan tests pass.

---

## Task 2: Add Admin Runtime API

**CodeGraph preflight:**

```powershell
codegraph explore "backend auth require_role admin runtime api router settings controls" --max-files 8
```

**Files:**

- Add: `scada-reporter/backend/app/api/runtime.py`
- Modify: `scada-reporter/backend/app/main.py`
- Add/modify backend tests.

**Steps:**

- [ ] Add `GET /api/runtime/status`.
- [ ] Add `POST /api/runtime/collector/start`.
- [ ] Add `POST /api/runtime/collector/stop`.
- [ ] Add `POST /api/runtime/scheduler/start`.
- [ ] Add `POST /api/runtime/scheduler/stop`.
- [ ] Protect all endpoints with `require_role("admin")`.
- [ ] Include backend uptime/start time in status.

**Verification:**

- [ ] Admin can call status and actions.
- [ ] Non-admin gets 403.
- [ ] Responses include collector, scheduler, and backend fields.

---

## Task 3: Add Frontend API Adapter

**CodeGraph preflight:**

```powershell
codegraph explore "frontend Settings page api client runtime health admin card tests" --max-files 10
```

**Files:**

- Modify: `scada-reporter/frontend/src/api/client.ts`

**Steps:**

- [ ] Add `RuntimeStatus` type.
- [ ] Add `getRuntimeStatus()`.
- [ ] Add `startCollector()`.
- [ ] Add `stopCollector()`.
- [ ] Add `startScheduler()`.
- [ ] Add `stopScheduler()`.

**Verification:**

- [ ] TypeScript compile passes.

---

## Task 4: Add Settings Runtime Card

**Files:**

- Add: `scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx`
- Modify: `scada-reporter/frontend/src/pages/Settings.tsx`
- Modify locale files under `scada-reporter/frontend/src/i18n/locales/*/settings.json`
- Add/modify frontend tests if current testing pattern supports it.

**Steps:**

- [ ] Render card only for admin.
- [ ] Fetch status on mount.
- [ ] Refresh status after each action.
- [ ] Add collector start/stop button.
- [ ] Add scheduler start/stop button.
- [ ] Show backend uptime and start time.
- [ ] Disable buttons during actions.
- [ ] Render inline errors.
- [ ] Add translation keys for all supported locales.

**Verification:**

- [ ] Settings tests pass.
- [ ] i18n parity tests pass.
- [ ] TypeScript compile passes.

---

## Task 5: Final Review and Merge

**Steps:**

- [ ] Run targeted backend tests.
- [ ] Run targeted frontend tests.
- [ ] Run `git diff --check`.
- [ ] Confirm unrelated dirty files are not staged.
- [ ] Commit on `feature/runtime-controls-settings`.
- [ ] Merge to `master` only after verification passes.

**Suggested final verification:**

```powershell
scada-reporter/backend/.venv/Scripts/python -m pytest scada-reporter/backend/tests/test_runtime_control.py scada-reporter/backend/tests/test_scheduler_lifespan.py -q
cd scada-reporter/frontend && pnpm tsc --noEmit
cd scada-reporter/frontend && pnpm test -- Settings
git diff --check
```
