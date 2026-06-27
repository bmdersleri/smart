# Settings Runtime Controls UX Improvements Plan

> Based on `docs/superpowers/specs/2026-06-27-settings-runtime-controls-ux-design.md`.

**Goal:** Improve the existing Settings runtime controls card with auto-refresh, last-updated feedback, action result messages, and more actionable error text.

**Branch:** `feature/runtime-controls-ux`

## Constraints

- Keep the backend API unchanged.
- Keep controls admin-only.
- Do not change runtime lifecycle semantics.
- Keep the UI compact and consistent with the existing Settings page.
- Do not commit unrelated dirty files.

---

## Task 1: Improve Runtime Card State Handling

**Files:**

- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx`

**Steps:**

- [x] Add reusable refresh logic.
- [x] Track `lastUpdatedAt`.
- [x] Add 10 second auto-refresh while mounted.
- [x] Avoid replacing the card with the loading state after the initial load.
- [x] Keep action buttons disabled while a request is in flight.

**Verification:**

- [x] Card still loads successfully.
- [x] Status updates after each successful poll.

---

## Task 2: Add User Feedback

**Files:**

- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx`
- Locale files if new labels are needed.

**Steps:**

- [x] Show a "Last updated" row or compact footer.
- [x] Show a success/result message after start/stop actions.
- [x] Clear stale result messages when a new action starts.
- [x] Improve error formatting with HTTP status and backend detail when available.

**Verification:**

- [x] Existing translated fallback strings still appear when no detail is available.
- [x] API response details are visible for structured failures.

---

## Task 3: Update Tests

**Files:**

- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.test.tsx`

**Steps:**

- [x] Cover last-updated display after load.
- [x] Cover action result message.
- [x] Cover detailed error display.
- [x] Cover polling refresh behavior if test timers are already used or easy to add.

**Verification:**

- [x] `pnpm vitest run src/pages/SettingsRuntimeCard.test.tsx`
- [x] `pnpm vitest run src/i18n/parity.test.ts`
- [x] `pnpm tsc --noEmit`

---

## Task 4: Finalize

**Steps:**

- [x] Review diff for unrelated changes.
- [x] Run targeted frontend checks.
- [ ] Commit with a focused conventional commit message.
- [ ] Push `feature/runtime-controls-ux`.
