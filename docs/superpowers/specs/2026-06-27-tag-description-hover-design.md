# Tag Description Hover Design

**Goal:** Add tag `description` editing to the Tag Management edit modal and expose the description as a short hover preview on tag names in the table view.

## Scope

This change is limited to the frontend tag management experience in `scada-reporter/frontend`.

The intended behavior is:

1. Users can edit a tag description from the existing edit modal.
2. The table view shows a hover preview on the tag name cell when a description exists.
3. The hover preview is short and unobtrusive, so the table density stays intact.
4. If a tag has no description, no tooltip UI is shown.

## Files In Scope

- `scada-reporter/frontend/src/pages/Tags.tsx`
- `scada-reporter/frontend/src/api/client.ts`
- `scada-reporter/frontend/src/i18n/locales/en/tags.json`
- `scada-reporter/frontend/src/i18n/locales/tr/tags.json`
- `scada-reporter/frontend/src/i18n/locales/de/tags.json`
- `scada-reporter/frontend/src/i18n/locales/ru/tags.json`
- `scada-reporter/frontend/src/i18n/locales/ar/tags.json`
- `scada-reporter/frontend/src/pages/Tags.i18n.test.tsx`

## Design

### Edit Modal

The existing `EditTagModal` already patches `unit`, `device`, `channel`, `deadband`, and group membership. The modal will gain one more controlled input for `description`.

Behavior:

- The field should be prefilled from `tag.description`.
- Saving should send `description` through `updateTag`.
- Clearing the field should persist an empty value or `null` according to the backend contract already used by the API layer.

The field should sit near the existing editable metadata, not below the save buttons, so the form remains easy to scan.

### Table Hover Preview

The table view should render the tag name cell as the hover target.

Behavior:

- When `row.description` is present, hovering the name shows a compact tooltip anchored near the cell.
- The tooltip should wrap long text and stay within a constrained width so it does not distort the table layout.
- The tooltip should disappear on mouse leave and should not block row actions.
- If there is no description, the name behaves like normal text without extra hover affordance.

Recommended interaction:

- Use an inline, CSS-driven hover container rather than a global popover system.
- Keep the markup local to the row so the behavior stays easy to reason about and does not require shared overlay state.

### Data Shape

The frontend tag model must include `description` so both the edit modal and the table renderer can read it directly.

This is a presentation-layer fix only. No backend schema or API contract change is expected if the backend already returns the field. If the current `Tag` response omits `description`, that would be handled as a separate backend task.

### Copy

New i18n strings are needed for:

- the description field label in the edit modal
- a short tooltip label or helper title if the hover preview uses one

Translations must be added consistently across the existing locale set so the i18n parity tests stay green.

## Acceptance Criteria

- The edit modal can display, edit, and save `description`.
- The tag name cell shows a short hover preview only when a description exists.
- Table density and existing action buttons remain unchanged.
- All locale files stay in parity for the added keys.
- Existing Tag page i18n tests still pass, and the new behavior has coverage for description rendering.

## Testing Notes

Primary tests to update:

- `Tags.i18n.test.tsx` for the new label and any text that appears in the rendered modal or table.
- Component-level behavior tests for the tooltip visibility and modal save path, if the existing Tag page test setup can cover them cleanly.

Manual verification should include:

- opening the edit modal for a tag with a description
- saving a modified description
- hovering a name cell with a description and confirming the preview appears
- checking a tag without description to confirm there is no tooltip noise
