# Settings Runtime Controls Audit and Confirmations — Design Spec

**Date:** 2026-06-27
**Status:** Proposed
**Scope:** Add audit logging for successful runtime start/stop actions and add stop confirmation prompts in the Settings runtime controls UI.

## 1. Goal

Make runtime controls safer and more traceable:

- Record who started or stopped the collector.
- Record who started or stopped the scheduler.
- Include previous and resulting running state in the audit detail.
- Ask for confirmation before stop actions that can interrupt data collection or scheduled reports.

## 2. Non-Goals

- Do not create a new audit table.
- Do not add a runtime audit viewer in this increment.
- Do not require confirmation for start actions.
- Do not change runtime lifecycle behavior.
- Do not add backend process start/stop.

## 3. Backend Design

Reuse the existing `audit_logs` table and `record_audit` helper.

Runtime action names:

- `runtime.collector.start`
- `runtime.collector.stop`
- `runtime.scheduler.start`
- `runtime.scheduler.stop`

Audit row fields:

- `actor_user_id`: current admin ID
- `actor_username`: current admin username
- `target_type`: `runtime_component`
- `target_id`: `collector` or `scheduler`
- `detail`: JSON object with component, requested action, previous running state, resulting running state
- `ip`: request client IP when available

Only successful mutations should be logged. If the runtime action raises an exception, the endpoint should not write an audit row.

## 4. Frontend Design

For stop actions only:

- Collector stop confirmation text should state that live data collection will pause.
- Scheduler stop confirmation text should state that scheduled report jobs will pause.
- If the user cancels, do not call the backend and do not alter visible status.

Use the project's existing lightweight confirmation pattern (`window.confirm`) for this increment.

## 5. Verification

Backend:

```powershell
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_runtime_api.py tests/test_audit_log.py -q
```

Frontend:

```powershell
cd scada-reporter/frontend
pnpm vitest run src/pages/SettingsRuntimeCard.test.tsx
pnpm vitest run src/i18n/parity.test.ts
pnpm tsc --noEmit
```

Acceptance:

- Runtime API tests assert audit rows for successful start/stop actions.
- Settings card tests assert stop confirmation can cancel a stop action.
- Locale parity remains green.
