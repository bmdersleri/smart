# Settings Runtime Controls Audit and Confirmations Plan

> Based on `docs/superpowers/specs/2026-06-27-settings-runtime-controls-audit-confirm-design.md`.

**Goal:** Add audit rows for successful runtime mutations and confirmation prompts for stop actions.

**Branch:** `feature/runtime-controls-audit-confirm`

## Constraints

- Reuse the existing audit log table.
- Do not change runtime status response shape.
- Do not require confirmation for start actions.
- Keep controls admin-only and writable-license guarded.
- Do not commit unrelated dirty files.

---

## Task 1: Add Runtime Audit Logging

**Files:**

- `scada-reporter/backend/app/api/runtime.py`
- `scada-reporter/backend/tests/test_runtime_api.py`

**Steps:**

- [x] Add request and DB dependencies to runtime mutation endpoints.
- [x] Capture runtime status before each mutation.
- [x] Execute the runtime mutation.
- [x] Capture runtime status after the mutation.
- [x] Write an audit row with component/action/before/after details.
- [x] Commit the DB transaction after adding the audit row.
- [x] Assert audit rows in runtime API tests.

**Verification:**

- [x] Runtime API tests pass.
- [x] Existing audit log tests pass.

---

## Task 2: Add Stop Confirmations

**Files:**

- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx`
- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.test.tsx`
- `scada-reporter/frontend/src/i18n/locales/*/settings.json`

**Steps:**

- [x] Add collector stop confirmation string.
- [x] Add scheduler stop confirmation string.
- [x] Prompt before collector stop.
- [x] Prompt before scheduler stop.
- [x] Add test coverage for canceling a stop.

**Verification:**

- [x] Runtime card tests pass.
- [x] i18n parity tests pass.
- [x] TypeScript compile passes.

---

## Task 3: Finalize

**Steps:**

- [x] Run targeted backend checks.
- [x] Run targeted frontend checks.
- [x] Run `git diff --check`.
- [ ] Commit with a focused conventional commit message.
- [ ] Push `feature/runtime-controls-audit-confirm`.
