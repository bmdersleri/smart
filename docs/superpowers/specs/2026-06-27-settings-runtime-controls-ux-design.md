# Settings Runtime Controls UX Improvements — Design Spec

**Date:** 2026-06-27
**Status:** Proposed
**Scope:** Improve the existing admin-only Settings runtime controls card without changing the backend runtime-control API contract.

## 1. Goal

Make the runtime controls card more useful during operations:

- Refresh runtime status automatically while the card is visible.
- Show when the status was last refreshed.
- Show a short result message after collector or scheduler start/stop actions.
- Preserve the current inline error behavior, but include useful HTTP status or backend detail when available.

## 2. Non-Goals

- Do not add new backend runtime endpoints.
- Do not change collector or scheduler lifecycle semantics.
- Do not expose controls to non-admin users.
- Do not add full backend process start/stop.
- Do not add audit logging in this increment.

## 3. Current Behavior

The card currently:

- Fetches status on mount.
- Shows backend uptime and start time.
- Allows admins to start or stop collector and scheduler.
- Refreshes after actions.
- Shows generic translated load/action failure messages.

When the backend has changed but the process has not been restarted, the UI only shows the generic load failure. When another client changes runtime state, the card does not update until the user reloads or performs an action.

## 4. Desired Behavior

Status loading:

- Fetch once on mount.
- Poll every 10 seconds while mounted.
- Do not show the full loading state after the first successful load.
- Update `lastUpdatedAt` after each successful status response.

Actions:

- Keep buttons disabled while an action is in flight.
- Update the card from the action response immediately.
- Refresh status after the action to confirm state.
- Show a success/result message such as "Collector stopped" or "Scheduler started".
- Clear stale success messages when a new action starts.

Errors:

- Use the existing translated fallback messages.
- Append useful details when an Axios response provides them:
  - HTTP status code.
  - `detail` from a JSON error response.
- Keep messages short enough for the Settings card.

## 5. Frontend Design

Recommended file ownership:

- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.tsx`
- `scada-reporter/frontend/src/pages/SettingsRuntimeCard.test.tsx`
- Locale files under `scada-reporter/frontend/src/i18n/locales/*/settings.json` only for new labels.

Add local state:

```ts
const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)
const [message, setMessage] = useState<string | null>(null)
```

Add helpers:

- `formatApiError(error, fallback)` for concise status/detail display.
- `refresh({ initial?: boolean })` for reusable status fetches.
- A small action-result label helper based on target and next state.

Polling:

- Use `setInterval(refresh, 10000)` in `useEffect`.
- Guard state updates after unmount.
- Avoid overlapping polling requests where practical.

## 6. Verification

Targeted checks:

```powershell
cd scada-reporter/frontend
pnpm test -- SettingsRuntimeCard
pnpm test -- i18n/parity.test.ts
pnpm tsc --noEmit
```

Manual check:

- Open Settings as admin.
- Confirm the card shows "Last updated".
- Stop/start collector and scheduler.
- Confirm a short result message appears.
- Confirm status refreshes without a full page reload.
