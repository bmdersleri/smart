# Tag Description Hover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tag `description` editing to the Tag Management edit modal and show that description as a compact hover preview on tag names in the table view.

**Architecture:** Keep the change local to the existing Tags page. Expand the frontend `Tag` type so it can read the backend `description` field, add a `textarea` to `EditTagModal`, and introduce a small local hover wrapper for the table name cell. The tooltip should be rendered inline in the row, not as a global overlay, but the table card must not clip it, so the wrapper around the table needs `overflow-visible`. Locale strings stay in the `tags` namespace.

**Tech Stack:** React 19 / TypeScript / TanStack Query / i18next / Vitest / Testing Library.

## Global Constraints

- Do not touch unrelated dirty files in the worktree.
- Do not change backend code or generated OpenAPI files for this feature; the backend already exposes `description`.
- Keep the change scoped to the Tag Management page and its related frontend tests/locales.
- Preserve the current edit/save flow for `unit`, `device`, `channel`, `deadband`, and group membership.

---

## File Structure

- `scada-reporter/frontend/src/api/client.ts` - extend the `Tag` response type so the page can read `description`.
- `scada-reporter/frontend/src/pages/Tags.tsx` - add the edit-modal `textarea`, save payload wiring, and the table hover preview.
- `scada-reporter/frontend/src/pages/Tags.description.test.tsx` - new interaction test for hover preview and description editing.
- `scada-reporter/frontend/src/pages/Tags.i18n.test.tsx` - extend the existing i18n coverage to include the new description label.
- `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/tags.json` - add the new field label string in every locale.

---

## Task 1: Wire `description` into the page and add the hover preview

**Files:**

- Modify: `scada-reporter/frontend/src/api/client.ts`
- Modify: `scada-reporter/frontend/src/pages/Tags.tsx`
- Add: `scada-reporter/frontend/src/pages/Tags.description.test.tsx`

**Interfaces:**

- Produces: `Tag.description` available in the page model; edit modal writes `description`; table name cell shows a hover tooltip only when `description` is non-empty.

- [ ] **Step 1: Write the failing interaction test**

Create `scada-reporter/frontend/src/pages/Tags.description.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import Tags from './Tags'
import type { Tag } from '../api/client'

const sampleTag: Tag = {
  id: 1,
  node_id: 'ns=2;s=PRESSURE_1',
  name: 'Influent Pressure',
  description: 'Live pressure at the inlet manifold.',
  unit: 'bar',
  device: 'P-101',
  channel: 'AI-1',
  is_active: true,
  group_id: null,
  min_alarm: null,
  max_alarm: null,
  deadband: null,
  plc_name: 'PLC-1',
  plc_ip: null,
  s7_address: 'DB1,REAL0',
  data_type: 'float32',
  sample_interval: 5,
  long_term: true,
  daily_tracking: false,
}

const getTags = vi.fn()
const getGroups = vi.fn()
const getGroupTree = vi.fn()
const updateTag = vi.fn()

vi.mock('../api/client', () => ({
  getTags,
  getGroups,
  getGroupTree,
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  updateTag,
  importTags: vi.fn(),
  importTagsCsv: vi.fn(),
  exportTags: vi.fn(),
  createGroup: vi.fn(),
  deleteGroup: vi.fn(),
  assignTagsToGroup: vi.fn(),
  unassignTags: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', role: 'admin', full_name: 'Admin', language: 'en' },
    can: () => true,
  }),
}))

function renderTags() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Tags />
    </QueryClientProvider>
  )
}

describe('Tags description hover', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    getTags.mockResolvedValue({ data: [sampleTag] })
    getGroups.mockResolvedValue({ data: [] })
    getGroupTree.mockResolvedValue({ data: [] })
    updateTag.mockResolvedValue({ data: sampleTag })
  })

  it('shows a tooltip when hovering a tag name with a description', async () => {
    const user = userEvent.setup()
    renderTags()

    await screen.findByText(sampleTag.name)
    expect(screen.queryByRole('tooltip')).toBeNull()

    await user.hover(screen.getByText(sampleTag.name))
    expect(await screen.findByRole('tooltip')).toHaveTextContent(sampleTag.description)

    await user.unhover(screen.getByText(sampleTag.name))
    await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull())
  })

  it('prefills and saves description in the edit modal', async () => {
    const user = userEvent.setup()
    renderTags()

    await screen.findByText(sampleTag.name)
    await user.click(screen.getByRole('button', { name: /edit/i }))

    const field = screen.getByLabelText(/description/i)
    expect(field).toHaveValue(sampleTag.description)

    await user.clear(field)
    await user.type(field, 'Updated description for operator use.')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(updateTag).toHaveBeenCalledWith(
        sampleTag.id,
        expect.objectContaining({ description: 'Updated description for operator use.' }),
      ),
    )
  })
})
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pnpm vitest run src/pages/Tags.description.test.tsx`

Expected: fail because `description` is not yet exposed in the page model, the edit modal has no description field, and the table row has no tooltip behavior.

- [ ] **Step 3: Implement the frontend behavior**

In `scada-reporter/frontend/src/api/client.ts`, extend the `Tag` interface:

```ts
export interface Tag {
  id: number; node_id: string; name: string; description: string; unit: string; device: string; channel: string
  is_active: boolean; group_id: number | null
  min_alarm: number | null; max_alarm: number | null; deadband: number | null
  plc_name: string; plc_ip: string | null; s7_address: string | null; data_type: string
  sample_interval: number; long_term: boolean; daily_tracking: boolean
  current_value?: number | null; quality?: number | null; read_at?: string | null
}
```

In `scada-reporter/frontend/src/pages/Tags.tsx`:

```tsx
function TagDescriptionCell({ name, description }: { name: string; description: string }) {
  const [open, setOpen] = useState(false)

  if (!description) {
    return <span className="truncate flex-1">{name}</span>
  }

  return (
    <span
      className="relative min-w-0 flex-1 cursor-help"
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span className="block truncate">{name}</span>
      {open && (
        <span
          role="tooltip"
          className="absolute start-0 top-full z-30 mt-2 max-w-80 rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xs text-gray-200 shadow-xl whitespace-pre-wrap break-words"
        >
          {description}
        </span>
      )}
    </span>
  )
}
```

Use that helper in the table row name cell:

```tsx
<td className="px-4 py-3 text-sm font-medium text-white">
  <div className="flex min-w-0 items-center gap-1.5">
    <TagDescriptionCell name={row.name} description={row.description ?? ''} />
    {row.long_term && <span className="ms-2 text-[10px] px-1.5 py-0.5 rounded bg-blue-900/50 text-blue-300">{t('badge_long_term')}</span>}
    {row.daily_tracking && <span className="ms-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-900/50 text-purple-300">{t('badge_daily')}</span>}
  </div>
</td>
```

Add a `textarea` to `EditTagModal`:

```tsx
const [description, setDescription] = useState(tag.description ?? '')

<div>
  <label className="text-xs text-gray-400 mb-1 block">{t('field_description')}</label>
  <textarea
    className={inputCls}
    rows={4}
    value={description}
    onChange={(e) => setDescription(e.target.value)}
  />
</div>
```

And include it in the save payload:

```tsx
const save = () =>
  mut.mutate({
    unit,
    device,
    channel,
    deadband: deadband === '' ? null : Number(deadband),
    description,
  })
```

Because the tooltip is absolutely positioned, change the table card wrapper from `overflow-hidden` to `overflow-visible` so the hover preview is not clipped.

- [ ] **Step 4: Run the test and confirm it passes**

Run: `pnpm vitest run src/pages/Tags.description.test.tsx`

Expected: pass with the tooltip and modal description assertions green.

- [ ] **Step 5: Commit the feature slice**

```bash
git checkout master
git add scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/Tags.tsx scada-reporter/frontend/src/pages/Tags.description.test.tsx
git commit -m "feat(tags): add description hover preview" -- scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/pages/Tags.tsx scada-reporter/frontend/src/pages/Tags.description.test.tsx
```

---

## Task 2: Localize the new label and extend i18n coverage

**Files:**

- Modify: `scada-reporter/frontend/src/i18n/locales/en/tags.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/tr/tags.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/de/tags.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ru/tags.json`
- Modify: `scada-reporter/frontend/src/i18n/locales/ar/tags.json`
- Modify: `scada-reporter/frontend/src/pages/Tags.i18n.test.tsx`

**Interfaces:**

- Produces: `field_description` string in every locale; i18n tests verify the label is actually rendered in English and Turkish.

- [ ] **Step 1: Add the new locale key**

Add `field_description` to each `tags.json` file:

```json
{
  "field_description": "Description"
}
```

Suggested translations:

- `en`: `Description`
- `tr`: `Açıklama`
- `de`: `Beschreibung`
- `ru`: `Описание`
- `ar`: `الوصف`

Place the key next to the other modal field labels so the file stays readable.

- [ ] **Step 2: Extend the existing i18n test**

Update `scada-reporter/frontend/src/pages/Tags.i18n.test.tsx` so it also opens the edit modal for a sampled tag and checks the new field label in both English and Turkish. Reuse the same tag fixture shape as Task 1, but keep the fixture local to this file so the test is self-contained.

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import Tags from './Tags'
import type { Tag } from '../api/client'

const sampleTag: Tag = {
  id: 1,
  node_id: 'ns=2;s=PRESSURE_1',
  name: 'Influent Pressure',
  description: 'Live pressure at the inlet manifold.',
  unit: 'bar',
  device: 'P-101',
  channel: 'AI-1',
  is_active: true,
  group_id: null,
  min_alarm: null,
  max_alarm: null,
  deadband: null,
  plc_name: 'PLC-1',
  plc_ip: null,
  s7_address: 'DB1,REAL0',
  data_type: 'float32',
  sample_interval: 5,
  long_term: true,
  daily_tracking: false,
}

const getTags = vi.fn()
const getGroups = vi.fn()
const getGroupTree = vi.fn()

vi.mock('../api/client', () => ({
  getTags,
  getGroups,
  getGroupTree,
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  updateTag: vi.fn(),
  importTags: vi.fn(),
  importTagsCsv: vi.fn(),
  exportTags: vi.fn(),
  createGroup: vi.fn(),
  deleteGroup: vi.fn(),
  assignTagsToGroup: vi.fn(),
  unassignTags: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', role: 'admin', full_name: 'Admin', language: 'en' },
    can: () => true,
  }),
}))

function renderTags() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Tags />
    </QueryClientProvider>
  )
}

beforeEach(async () => {
  await i18n.changeLanguage('en')
  getTags.mockResolvedValue({ data: [sampleTag] })
  getGroups.mockResolvedValue({ data: [] })
  getGroupTree.mockResolvedValue({ data: [] })
})

it('renders the description label in English and Turkish', async () => {
  const user = userEvent.setup()

  await i18n.changeLanguage('en')
  renderTags()
  await screen.findByText(sampleTag.name)
  await user.click(screen.getByRole('button', { name: /edit/i }))
  expect(screen.getByLabelText('Description')).toBeTruthy()

  cleanup()

  await i18n.changeLanguage('tr')
  renderTags()
  await screen.findByText(sampleTag.name)
  await user.click(screen.getByRole('button', { name: /edit/i }))
  expect(screen.getByLabelText('Açıklama')).toBeTruthy()
})
```

Keep the existing header and raw-namespace-key assertions so the page still has basic namespace hygiene coverage.

- [ ] **Step 3: Run the frontend checks**

Run:

```bash
pnpm vitest run src/pages/Tags.description.test.tsx src/pages/Tags.i18n.test.tsx src/pages/Tags.gating.test.tsx
pnpm tsc -b
pnpm lint
```

Expected:

- All targeted Vitest files pass.
- TypeScript build passes with no new errors.
- Lint passes on the touched files.

- [ ] **Step 4: Manual browser verification**

Run the frontend dev server, open the Tags page, and verify all of the following in the browser:

1. A tag with a description shows a compact hover preview on the tag name in the table view.
2. The tooltip stays visually contained and does not collide with the row actions.
3. The edit modal shows the description textarea with the current value prefilled.
4. A tag without a description does not show a tooltip.

- [ ] **Step 5: Commit the locale and test follow-up**

```bash
git checkout master
git add scada-reporter/frontend/src/i18n/locales/en/tags.json scada-reporter/frontend/src/i18n/locales/tr/tags.json scada-reporter/frontend/src/i18n/locales/de/tags.json scada-reporter/frontend/src/i18n/locales/ru/tags.json scada-reporter/frontend/src/i18n/locales/ar/tags.json scada-reporter/frontend/src/pages/Tags.i18n.test.tsx
git commit -m "fix(tags): localize description label and i18n coverage" -- scada-reporter/frontend/src/i18n/locales/en/tags.json scada-reporter/frontend/src/i18n/locales/tr/tags.json scada-reporter/frontend/src/i18n/locales/de/tags.json scada-reporter/frontend/src/i18n/locales/ru/tags.json scada-reporter/frontend/src/i18n/locales/ar/tags.json scada-reporter/frontend/src/pages/Tags.i18n.test.tsx
```

---

## Self-Review

**Spec coverage:**

- Edit modal description field and save path -> Task 1.
- Table hover preview on tag name -> Task 1.
- No tooltip when description is empty -> Task 1 helper logic and manual browser check.
- Locale coverage for the new label -> Task 2.
- Existing i18n hygiene -> Task 2 keeps the namespace leak checks.

**Placeholder scan:**

- No "TBD", "TODO", or vague "add appropriate handling" steps.
- The tooltip implementation is described as a concrete local helper, not an abstract overlay system.

**Type consistency:**

- `Tag.description` is added once in `api/client.ts` and then consumed in `Tags.tsx` and the tests.
- `field_description` is the only new locale key and is referenced by both the modal and the i18n test.
- The tooltip helper returns a `role="tooltip"` node, so the behavior test can target it without relying on brittle class assertions.
