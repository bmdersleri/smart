# Reports Merge Design

Date: 2026-06-29
Status: Approved for implementation planning
Scope: Frontend navigation and page composition for Reports and Advanced Reports

## Context

The frontend currently exposes two separate report experiences:

- `frontend/src/pages/Reports.tsx` handles ad-hoc report generation and recent history download.
- `frontend/src/pages/AdvancedReports.tsx` handles reusable templates, scheduled runs, and archive browsing.

These surfaces are conceptually related but split across separate sidebar items and routes:

- `/reports`
- `/advanced-reports`

The backend API is also split, but by responsibility rather than user intent:

- `/api/reports/*` for ad-hoc report generation and history
- `/api/advanced-reports/*` for templates, scheduling, and archive

The goal is to unify the user experience into one report center without expanding backend scope or breaking existing behavior.

## Goals

- Present all reporting workflows under a single `Raporlar` navigation item.
- Make `/reports` the canonical reporting entrypoint.
- Keep ad-hoc reporting as the default visible experience.
- Preserve advanced reporting capabilities inside the same page as secondary tabs.
- Avoid backend contract changes in the first implementation.
- Avoid breaking old deep links to `/advanced-reports`.

## Non-Goals

- No backend endpoint rename or consolidation in this phase.
- No advanced report data-model changes.
- No redesign of report generation logic.
- No permission model changes.
- No attempt to merge ad-hoc history and advanced archive into one backend list.

## Selected Approach

Use a single frontend page at `/reports` as a tabbed report center.

The page contains four tabs:

- `quick`: existing ad-hoc reporting UI from `Reports.tsx`
- `templates`: existing template management UI from `AdvancedReports.tsx`
- `scheduled`: existing scheduled report UI from `AdvancedReports.tsx`
- `archive`: existing archive UI from `AdvancedReports.tsx`

Default tab behavior:

- `/reports` opens the `quick` tab by default.
- Legacy `/advanced-reports` redirects to `/reports` and also lands on the `quick` tab.

This is intentionally conservative. It removes user-facing duplication in navigation while keeping the backend APIs and most page-level logic intact.

## Alternatives Considered

### Option A: Frontend-only merge with tabbed report center

This is the selected option.

Pros:

- Lowest behavioral risk
- No backend contract migration
- Minimal blast radius for existing report logic
- Clear user-facing simplification

Cons:

- Backend naming remains split
- Some report concepts remain represented by separate query keys and API groups

### Option B: Full route and API consolidation under `/reports/*`

Not selected for this phase.

Pros:

- Cleaner long-term naming model
- Better conceptual consistency between frontend and backend

Cons:

- Larger scope
- More migration risk
- Requires OpenAPI/client regeneration and broader regression coverage

### Option C: Keep two routes but make one page link into the other

Not selected.

Pros:

- Very small implementation

Cons:

- Does not actually remove navigation duplication
- Preserves the current mental split for the user

## Architecture

### Canonical Route

`/reports` becomes the only primary reports route shown in the sidebar.

The route renders a unified page shell with:

- page title
- optional subtitle
- top-level tab navigation
- active tab content area

### Legacy Route Handling

`/advanced-reports` remains temporarily as a compatibility route only.

Behavior:

- it performs a redirect to `/reports`
- the destination uses the default `quick` tab

This keeps old bookmarks and internal references from failing while clearly moving users onto the canonical surface.

### UI Composition

The existing advanced reports page already has a tabbed internal structure:

- templates
- scheduled
- archive

The merge preserves that logic but flattens it into the unified reports page. The fast-report UI becomes the first tab in the combined page rather than remaining a separate standalone screen.

Implementation extracts tab content into focused components instead of copying large blocks of JSX into one file.

### Backend Boundaries

No backend route or payload changes are required.

The merged page continues to use:

- `getTags`
- `generateReport`
- `getReportHistory`
- `downloadHistoryReport`
- `listTemplates`
- `createTemplate`
- `updateTemplate`
- `deleteTemplate`
- `runTemplate`
- `listScheduled`
- `createScheduled`
- `toggleScheduled`
- `deleteScheduled`
- `getArchive`
- `downloadArchiveReport`

This preserves API and React Query behavior while changing only the presentation layer.

## File Structure

The implementation uses a clearer report-page composition.

Expected structure:

- `frontend/src/pages/Reports.tsx`
  - becomes the unified page shell
- `frontend/src/pages/AdvancedReports.tsx`
  - is reduced or retired after its tab content is extracted for reuse
- extracted report tab components under `frontend/src/pages/reports/`
  - `QuickReportTab.tsx`
  - `TemplatesTab.tsx`
  - `ScheduledTab.tsx`
  - `ArchiveTab.tsx`

The exact import/export boundaries can follow existing repo patterns, but the structural requirement is fixed: do not increase the size and coupling of already-large page files by merging both screens into one monolithic component.

## Navigation Changes

### Sidebar

In `frontend/src/components/Layout.tsx`:

- keep `nav_reports`
- remove `nav_advanced_reports`

Result:

- users see one reporting destination instead of two adjacent entries

### Router

In `frontend/src/App.tsx`:

- `/reports` renders the merged page
- `/advanced-reports` redirects to `/reports`

The redirect is explicit rather than silently rendering the same component under both paths. The route structure communicates that `/reports` is now canonical.

## Content Design

### Page Header

The merged page continues to use `Raporlar` as the primary title.

The subtitle describes the combined scope in plain operational language, for example:

- fast report export
- reusable templates
- scheduled runs
- archive access

The wording stays concise and aligned with the existing application tone.

### Tab Order

Required order:

1. `Hızlı Rapor`
2. `Şablonlar`
3. `Zamanlanmış`
4. `Arşiv`

Reasoning:

- ad-hoc reporting is the default and most immediate task
- templates and scheduling are more advanced configuration workflows
- archive is a downstream reference workflow

### Default State

The first render must show `Hızlı Rapor`.

This applies both when the user visits `/reports` directly and when they arrive via the legacy `/advanced-reports` redirect.

## Internationalization

Current translations are split between:

- `reports.json`
- `advancedReports.json`
- `common.json`

Required i18n changes:

- keep `reports` namespace as the owner of the merged page shell
- add tab labels for the merged page into `reports.json`
- keep advanced workflow strings in `advancedReports.json` unless they are promoted into the new shared shell
- remove sidebar dependency on `common.nav_advanced_reports`

The implementation must preserve translation parity across supported languages and avoid leaking raw namespace keys into the UI.

## State and Data Flow

The unified page does not require shared mutation state between all tabs beyond normal React Query cache invalidation.

Rules:

- quick report logic remains local to the quick tab
- template, scheduled, and archive logic continue to use their existing query keys
- running a template may still switch the active tab to `archive` after success if that is current behavior worth preserving

The merge is structural, not a state-model rewrite.

## Error Handling

- Existing error behavior in quick reports remains unchanged.
- Existing mutation and loading states in advanced report tabs remain unchanged.
- Redirect from `/advanced-reports` must never produce a blank page or routing loop.
- If advanced-report feature gating or permissions exist in the current UI flow, they must continue to work after the merge.

## Testing Strategy

### Frontend Routing Tests

- `/reports` renders the merged page and shows the quick-report tab by default
- `/advanced-reports` redirects to `/reports`
- redirect result still shows the quick-report tab by default

### UI Tests

- sidebar renders only one reports navigation item
- merged page tab bar renders all four tabs
- switching tabs reveals the expected content surface
- no raw i18n keys appear in the merged page

### Regression Coverage

- existing `AdvancedReports` i18n coverage is rewritten against the merged reports page
- translation parity tests must continue to pass after any new `reports.json` keys are added
- existing advanced report actions remain reachable after the merge

## Risks

### Large Component Risk

`AdvancedReports.tsx` is already large. A naive merge into `Reports.tsx` would create a harder-to-maintain page. The implementation extracts reusable tab components instead of pasting both files together.

### Hidden Route Dependencies

There may be tests, bookmarks, or user habits tied to `/advanced-reports`. Redirect coverage is required so the migration stays safe.

### Translation Drift

Merging the shell can easily duplicate or misplace strings across `reports` and `advancedReports` namespaces. Translation ownership must stay intentional.

## Acceptance Criteria

- The sidebar shows `Raporlar` but not `Gelişmiş Raporlar`.
- Visiting `/reports` opens the merged report center.
- The default visible tab is `Hızlı Rapor`.
- The page includes tabs for `Hızlı Rapor`, `Şablonlar`, `Zamanlanmış`, and `Arşiv`.
- Legacy `/advanced-reports` links do not break and redirect into `/reports`.
- Existing advanced report workflows remain usable from the merged page.
- No backend API or OpenAPI changes are required.
- Frontend tests cover the merged default tab, redirect behavior, and i18n rendering.

## Implementation Sequence

1. Extract or reorganize report tab content so the merged page can compose it cleanly.
2. Build the merged `Reports` page shell and make `quick` the default tab.
3. Update routing and sidebar navigation.
4. Update translations for the merged shell.
5. Update and add frontend tests for route, navigation, and i18n behavior.
