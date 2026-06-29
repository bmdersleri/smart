# Facility Variables UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React UI for facility variables — a management page (CRUD + block-based expression builder + preview), an advanced-report variable picker, and Excel-template column variable-binding controls — consuming the already-shipped Plan 1/2/3 backends.

**Architecture:** Three independent UI surfaces, each a bounded task group. The management page is a new route/page following the `Tags.tsx` CRUD convention (TanStack Query + modal forms + `useAuth().can` gating). The expression builder is a recursive block editor that EMITS the backend's JSON expression dict — it does NOT re-implement validation or bucketing; correctness comes from the backend `/validate` and `/preview` endpoints (single source of truth). The report-picker and Excel-binding surfaces are additive edits to existing editors (`AdvancedReports.tsx`, `ExcelTemplates.tsx` + `excelTemplates.helpers.ts`).

**Tech Stack:** React 19, Vite, Tailwind CSS v4, TanStack Query v5, axios (`src/api/client.ts` hand-written wrappers), react-i18next (5 locales: en/tr/ru/de/ar, parity-enforced), Vitest + @testing-library/react, lucide-react icons.

## Global Constraints

- **Frontend lives under `scada-reporter/frontend/`; all `pnpm`/`vitest` commands run from there.** Tests: `pnpm test` (Vitest). Typecheck: `pnpm tsc --noEmit` (or `just typecheck` from repo root runs both backends). Lint/format: Prettier 3.8.4.
- **No backend changes.** Every field this UI sends/reads already exists server-side (verified: report-template `variable_ids`, archive `variable_refs`, excel-column `source_type`/`variable_id`/`write_mode`/`reduce_op`/`target_mode`/`target_cell`). If a payload is rejected, the bug is in the frontend payload, not the backend — do not add/modify endpoints.
- **i18n parity is mandatory.** Every new key must exist in ALL 5 locales (`en/tr/ru/de/ar`) with identical key sets and identical `{{placeholder}}` tokens. `src/i18n/parity.test.ts` enforces this in CI — a missing key in any locale fails the suite. Add new namespaces to `src/i18n/index.ts` (5 imports + 5 resource entries + `ns` array) AND to `parity.test.ts` (5 imports + `NAMESPACES` entry).
- **Permission gating is exact-match.** `useAuth().can(perm)` returns true for `admin` role OR exact membership in `user.permissions`. No wildcards. The facility-variable write permissions are exactly `facility_variable:create`, `facility_variable:edit`, `facility_variable:delete` (there is NO `facility_variable:view` — read/preview/validate are open to any authenticated user). Gate create on `can('facility_variable:create')`, edit on `can('facility_variable:edit')`, delete on `can('facility_variable:delete')`.
- **One validation/evaluation path.** The expression builder produces the JSON dict only. Validation = `POST /facility-variables/validate`. Preview = `POST /facility-variables/{id}/preview`. Do NOT port the Python validator or bucketing to TypeScript. Showing the backend's error text is the contract.
- **API client convention.** `src/api/client.ts` is hand-written (NOT replaced by `just gen-client`). Add typed wrapper functions there following the existing `api.get<T>('/path')` pattern; the request interceptor attaches the Bearer token automatically — never pass it. List endpoints return `r.data` after `.then`.
- **CSS/RTL.** Reuse the shared `inputCls` string and the `fixed inset-0 …` modal shell from `Tags.tsx`. Use logical Tailwind props (`ms-`/`me-`/`ps-`/`pe-`/`start-`/`end-`) so Arabic RTL works via the `<html dir>` attribute (handled globally — no per-component RTL code).
- **TanStack Query keys** are plain string arrays. Use `['facility-variables']` for the variable list everywhere it is fetched (management page, report picker, excel binding) so one invalidation refreshes all consumers.

---

## File Structure

**New files:**
- `src/pages/FacilityVariables.tsx` — management page (list + modals).
- `src/pages/facilityVariables/ExpressionBuilder.tsx` — recursive block expression editor (emits the JSON dict).
- `src/pages/facilityVariables/PreviewPanel.tsx` — validate + preview (scalar value / series chart).
- `src/i18n/locales/{en,tr,ru,de,ar}/facilityVariables.json` — namespace strings (5 files).
- Test files colocated: `FacilityVariables.gating.test.tsx`, `facilityVariables/ExpressionBuilder.test.tsx`, `facilityVariables/PreviewPanel.test.tsx`, plus edits' tests.

**Modified files:**
- `src/api/client.ts` — facility-variable wrappers + types; `TemplateCreate` gains `variable_ids`.
- `src/i18n/index.ts`, `src/i18n/parity.test.ts` — register the `facilityVariables` namespace.
- `src/App.tsx` — route.
- `src/components/Layout.tsx` — sidebar nav item; `src/i18n/locales/*/common.json` — nav label.
- `src/pages/Users.tsx` + `src/i18n/locales/*/users.json` — permission labels.
- `src/pages/AdvancedReports.tsx` — `variable_ids` picker + preview count + archive `variable_refs` display.
- `src/pages/ExcelTemplates.tsx`, `src/pages/excelTemplates.helpers.ts` — column variable-binding fields + UI.
- `src/i18n/locales/*/advancedReports.json`, `src/i18n/locales/*/excelTemplates.json` — new keys.

---

## Backend Reference (verbatim — do not re-derive)

**Facility-variable endpoints** (base `/api/facility-variables`, trailing slash on collection):
| Method | Path | Auth | Body / Returns |
|---|---|---|---|
| GET | `/facility-variables/` | any auth | → `VariableResponse[]` |
| POST | `/facility-variables/` | `can('facility_variable:create')` + writable | `VariableCreate` → 201 `VariableResponse`; 409 dup code; 422 expr error |
| GET | `/facility-variables/{id}` | any auth | → `VariableResponse`; 404 |
| PUT | `/facility-variables/{id}` | `can('facility_variable:edit')` + writable | `VariableUpdate` → 200; 422 |
| DELETE | `/facility-variables/{id}?force=bool` | `can('facility_variable:delete')` + writable | → 204; 409 if referenced (retry `?force=true`) |
| POST | `/facility-variables/validate` | any auth | `{expression: dict, kind: str}` → 200 `{valid:true}`; 422 `{detail}` |
| POST | `/facility-variables/{id}/preview` | any auth | `PreviewRequest` → scalar/series; 422 |
| GET | `/facility-variables/{id}/dependencies` | any auth | → `{depends_on_type, depends_on_tag_id, depends_on_variable_id}[]` |

**VariableResponse fields:** `id:number, code:string, name:string, description:string, kind:'scalar'|'series', value_type:string, unit:string, expression:object, null_policy:string, quality_policy:string, default_time_grain:string|null, is_active:boolean, version:number, dependency_count:number, warnings:string[]`.

**VariableCreate body:** `code, name, kind` required; `description='' , unit='', value_type='number', null_policy='skip', quality_policy='good_only', default_time_grain='day'` defaulted; `expression:object` required.
**VariableUpdate body:** `name` required; `description, unit, null_policy, quality_policy, default_time_grain` defaulted; `expression:object` required. (`code` and `kind` are NOT updatable.)

**PreviewRequest body:** `{ window: { type:'month'|'custom', year?:number, month?:number, start?:ISOstring, end?:ISOstring }, grain?: string|null, tz_offset_hours?: number|null }`. Guards → 422: month without year+month; custom without start+end; `end<=start`; estimated points > 5000.
**Preview scalar response:** `{kind:'scalar', value:number|null, unit:string}`. **Preview series response:** `{kind:'series', points:{ts:string, value:number|null}[], unit:string}`.

**Expression node catalog** (every node has `op`; `EXPR_OPS = agg|series|const|round|abs|coalesce|moving_avg|reduce|ref|add|sub|mul|div`):
- `{op:'const', value:number}` — scalar
- `{op:'ref', variable_id:number}` — scalar
- `{op:'agg', source:{type:'tag',tag_id:number}, agg:AGG, window:string}` — scalar
- `{op:'series', source:{type:'tag',tag_id:number}, agg:AGG, grain:GRAIN, window:string}` — series
- `{op:'reduce', reduce:REDUCE, source:<series node>}` — scalar
- `{op:'moving_avg', window_size:int>=1, source:<series node>}` — series
- `{op:'round', ndigits:int, source:<node>}` — inherits source shape
- `{op:'abs', source:<node>}` — inherits source shape
- `{op:'add'|'sub'|'mul', args:<node>[]}` — series if any arg series else scalar
- `{op:'div', on_zero:'null'|'zero'|'fail', args:<node>[]}` — same
- `{op:'coalesce', args:<node>[]}` — same
- `AGG = sum|avg|min|max|last|delta`; `REDUCE = sum|avg|min|max|last`; `GRAIN = hour|day|week|month`; `window` is a free string (suggest `day`, `7d`, `30d`, `month`).

---

### Task 1: i18n namespace `facilityVariables` (5 locales) + registration

**Files:**
- Create: `src/i18n/locales/en/facilityVariables.json`, `.../tr/...`, `.../ru/...`, `.../de/...`, `.../ar/...`
- Modify: `src/i18n/index.ts`, `src/i18n/parity.test.ts`
- Modify: `src/i18n/locales/{en,tr,ru,de,ar}/common.json` (add `nav_facility_variables`)

**Interfaces:**
- Produces: the `facilityVariables` namespace, available via `useTranslation(['facilityVariables','common'])`, and the `common:nav_facility_variables` label. All later tasks consume these keys.

- [ ] **Step 1: Write the failing test**

`src/i18n/parity.test.ts` already asserts cross-locale parity for every registered namespace. Add `facilityVariables` to its `NAMESPACES` map (5 imports + one entry) FIRST so the suite fails until the 5 files exist with matching keys.

Add imports near the other namespace imports:
```ts
import fvEn from './locales/en/facilityVariables.json'
import fvTr from './locales/tr/facilityVariables.json'
import fvRu from './locales/ru/facilityVariables.json'
import fvDe from './locales/de/facilityVariables.json'
import fvAr from './locales/ar/facilityVariables.json'
```
Add to the `NAMESPACES` object (mirror an existing entry's shape exactly):
```ts
  facilityVariables: { en: fvEn, tr: fvTr, ru: fvRu, de: fvDe, ar: fvAr },
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- parity` (from `scada-reporter/frontend`)
Expected: FAIL — cannot resolve `./locales/en/facilityVariables.json`.

- [ ] **Step 3: Create the 5 locale files with identical key sets**

`src/i18n/locales/en/facilityVariables.json`:
```json
{
  "title": "Facility Variables",
  "subtitle": "User-managed report variables",
  "add": "+ Add Variable",
  "col_code": "Code",
  "col_name": "Name",
  "col_kind": "Kind",
  "col_unit": "Unit",
  "col_deps": "Dependencies",
  "col_status": "Status",
  "col_updated": "Updated",
  "col_actions": "Actions",
  "status_active": "Active",
  "status_inactive": "Inactive",
  "action_edit": "Edit",
  "action_duplicate": "Duplicate",
  "action_deactivate": "Deactivate",
  "action_preview": "Preview",
  "confirm_deactivate": "Deactivate variable \"{{name}}\"?",
  "deactivate_blocked": "Variable is used by a report and cannot be deactivated. Remove the binding first.",
  "empty": "No variables yet.",
  "kind_scalar": "Scalar",
  "kind_series": "Series",
  "step_basic": "Basic info",
  "step_expression": "Expression",
  "step_window": "Window & grain",
  "step_preview": "Preview",
  "field_code": "Code",
  "field_name": "Name",
  "field_description": "Description",
  "field_kind": "Kind",
  "field_unit": "Unit",
  "field_grain": "Default time grain",
  "field_null_policy": "Null policy",
  "field_quality_policy": "Quality policy",
  "builder_op": "Operation",
  "builder_add_arg": "+ Add operand",
  "builder_remove": "Remove",
  "builder_tag": "Tag",
  "builder_agg": "Aggregation",
  "builder_window": "Window",
  "builder_grain": "Grain",
  "builder_value": "Value",
  "builder_variable": "Variable",
  "builder_reduce": "Reduce",
  "builder_ndigits": "Decimals",
  "builder_window_size": "Window size",
  "builder_on_zero": "On divide-by-zero",
  "builder_window_help": "e.g. day, 7d, 30d, month",
  "validate": "Validate",
  "valid_ok": "Expression is valid.",
  "preview": "Preview",
  "preview_month": "Month",
  "preview_custom": "Custom range",
  "preview_year": "Year",
  "preview_start": "Start",
  "preview_end": "End",
  "preview_scalar": "Value",
  "preview_series_points": "{{count}} points",
  "preview_empty": "No preview yet.",
  "save": "Save",
  "saving": "Saving…",
  "create_title": "New variable",
  "edit_title": "Edit variable",
  "error_generic": "Operation failed.",
  "error_duplicate_code": "A variable with this code already exists."
}
```

Create `tr`, `ru`, `de`, `ar` with the SAME keys, translated values, and the SAME `{{name}}`/`{{count}}` placeholder tokens. Turkish values (use these verbatim for `tr`):
```json
{
  "title": "Tesis Değişkenleri",
  "subtitle": "Kullanıcı tanımlı rapor değişkenleri",
  "add": "+ Değişken Ekle",
  "col_code": "Kod",
  "col_name": "Ad",
  "col_kind": "Tür",
  "col_unit": "Birim",
  "col_deps": "Bağımlılık",
  "col_status": "Durum",
  "col_updated": "Güncellendi",
  "col_actions": "İşlemler",
  "status_active": "Aktif",
  "status_inactive": "Pasif",
  "action_edit": "Düzenle",
  "action_duplicate": "Çoğalt",
  "action_deactivate": "Pasifleştir",
  "action_preview": "Önizle",
  "confirm_deactivate": "\"{{name}}\" değişkeni pasifleştirilsin mi?",
  "deactivate_blocked": "Değişken bir raporda kullanılıyor, pasifleştirilemez. Önce bağlamayı kaldırın.",
  "empty": "Henüz değişken yok.",
  "kind_scalar": "Skaler",
  "kind_series": "Seri",
  "step_basic": "Temel bilgi",
  "step_expression": "İfade",
  "step_window": "Pencere & grain",
  "step_preview": "Önizleme",
  "field_code": "Kod",
  "field_name": "Ad",
  "field_description": "Açıklama",
  "field_kind": "Tür",
  "field_unit": "Birim",
  "field_grain": "Varsayılan zaman grain'i",
  "field_null_policy": "Null politikası",
  "field_quality_policy": "Kalite politikası",
  "builder_op": "İşlem",
  "builder_add_arg": "+ Operand ekle",
  "builder_remove": "Kaldır",
  "builder_tag": "Etiket",
  "builder_agg": "Toplama",
  "builder_window": "Pencere",
  "builder_grain": "Grain",
  "builder_value": "Değer",
  "builder_variable": "Değişken",
  "builder_reduce": "İndirgeme",
  "builder_ndigits": "Ondalık",
  "builder_window_size": "Pencere boyu",
  "builder_on_zero": "Sıfıra bölünmede",
  "builder_window_help": "örn. day, 7d, 30d, month",
  "validate": "Doğrula",
  "valid_ok": "İfade geçerli.",
  "preview": "Önizle",
  "preview_month": "Ay",
  "preview_custom": "Özel aralık",
  "preview_year": "Yıl",
  "preview_start": "Başlangıç",
  "preview_end": "Bitiş",
  "preview_scalar": "Değer",
  "preview_series_points": "{{count}} nokta",
  "preview_empty": "Henüz önizleme yok.",
  "save": "Kaydet",
  "saving": "Kaydediliyor…",
  "create_title": "Yeni değişken",
  "edit_title": "Değişken düzenle",
  "error_generic": "İşlem başarısız.",
  "error_duplicate_code": "Bu kod ile bir değişken zaten var."
}
```
For `ru`/`de`/`ar`, translate the English values (Arabic RTL handled globally). Keep keys + placeholders identical.

- [ ] **Step 4: Register the namespace in `src/i18n/index.ts`**

Add 5 imports mirroring the existing namespace imports:
```ts
import facilityVariablesEn from './locales/en/facilityVariables.json'
import facilityVariablesTr from './locales/tr/facilityVariables.json'
import facilityVariablesRu from './locales/ru/facilityVariables.json'
import facilityVariablesDe from './locales/de/facilityVariables.json'
import facilityVariablesAr from './locales/ar/facilityVariables.json'
```
Add `facilityVariables: <lang>Bundle` to each of the 5 locale objects in `resources`, and add `'facilityVariables'` to the `ns` array. (Match the surrounding pattern exactly — read the file first.)

- [ ] **Step 5: Add `nav_facility_variables` to all 5 `common.json`**

`en`: `"nav_facility_variables": "Facility Variables"`. `tr`: `"nav_facility_variables": "Tesis Değişkenleri"`. Translate ru/de/ar.

- [ ] **Step 6: Run the parity suite to verify it passes**

Run: `pnpm test -- parity`
Expected: PASS — all namespaces (incl. `facilityVariables`) parity-clean.

- [ ] **Step 7: Commit**

```bash
git add src/i18n
git commit -m "feat(facility-vars-ui): add facilityVariables i18n namespace (5 locales) + nav label"
```

---

### Task 2: API client wrappers + types

**Files:**
- Modify: `src/api/client.ts`
- Test: `src/api/__tests__/facilityVariables.client.test.ts`

**Interfaces:**
- Produces (all imported by later tasks):
  - Types: `FacilityVariable`, `FacilityVariableCreate`, `FacilityVariableUpdate`, `PreviewWindow`, `PreviewRequestBody`, `PreviewResult`, `VariableDependency`, `ExprNode`.
  - Functions: `listFacilityVariables()`, `getFacilityVariable(id)`, `createFacilityVariable(data)`, `updateFacilityVariable(id,data)`, `deleteFacilityVariable(id,force?)`, `validateExpression(body)`, `previewVariable(id,body)`, `getVariableDependencies(id)`.

- [ ] **Step 1: Write the failing test**

`src/api/__tests__/facilityVariables.client.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, listFacilityVariables, createFacilityVariable, updateFacilityVariable, deleteFacilityVariable, validateExpression, previewVariable } from '../client'

describe('facility variable client', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('GET list hits /facility-variables/', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] })
    await listFacilityVariables()
    expect(spy).toHaveBeenCalledWith('/facility-variables/')
  })
  it('POST create hits /facility-variables/ with body', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    const body = { code: 'v', name: 'V', kind: 'scalar' as const, expression: { op: 'const', value: 1 } }
    await createFacilityVariable(body)
    expect(spy).toHaveBeenCalledWith('/facility-variables/', body)
  })
  it('PUT update hits /facility-variables/{id}', async () => {
    const spy = vi.spyOn(api, 'put').mockResolvedValue({ data: {} })
    await updateFacilityVariable(7, { name: 'X', expression: { op: 'const', value: 1 } })
    expect(spy).toHaveBeenCalledWith('/facility-variables/7', { name: 'X', expression: { op: 'const', value: 1 } })
  })
  it('DELETE passes force as query param', async () => {
    const spy = vi.spyOn(api, 'delete').mockResolvedValue({ data: {} })
    await deleteFacilityVariable(7, true)
    expect(spy).toHaveBeenCalledWith('/facility-variables/7?force=true')
  })
  it('validate posts expression+kind', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { valid: true } })
    await validateExpression({ expression: { op: 'const', value: 1 }, kind: 'scalar' })
    expect(spy).toHaveBeenCalledWith('/facility-variables/validate', { expression: { op: 'const', value: 1 }, kind: 'scalar' })
  })
  it('preview posts to /{id}/preview', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { kind: 'scalar', value: 1, unit: '' } })
    await previewVariable(3, { window: { type: 'month', year: 2026, month: 6 } })
    expect(spy).toHaveBeenCalledWith('/facility-variables/3/preview', { window: { type: 'month', year: 2026, month: 6 } })
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- facilityVariables.client`
Expected: FAIL — exports do not exist.

- [ ] **Step 3: Add types + wrappers to `src/api/client.ts`**

Append near the other entity wrappers (after the existing exports — read the file's end first to place it consistently):
```ts
// --- Facility variables -----------------------------------------------------
export type ExprNode = Record<string, unknown>

export interface FacilityVariable {
  id: number
  code: string
  name: string
  description: string
  kind: 'scalar' | 'series'
  value_type: string
  unit: string
  expression: ExprNode
  null_policy: string
  quality_policy: string
  default_time_grain: string | null
  is_active: boolean
  version: number
  dependency_count: number
  warnings: string[]
}

export interface FacilityVariableCreate {
  code: string
  name: string
  description?: string
  kind: 'scalar' | 'series'
  unit?: string
  value_type?: string
  expression: ExprNode
  null_policy?: string
  quality_policy?: string
  default_time_grain?: string | null
}

export interface FacilityVariableUpdate {
  name: string
  description?: string
  unit?: string
  expression: ExprNode
  null_policy?: string
  quality_policy?: string
  default_time_grain?: string | null
}

export interface PreviewWindow {
  type: 'month' | 'custom'
  year?: number
  month?: number
  start?: string
  end?: string
}
export interface PreviewRequestBody {
  window: PreviewWindow
  grain?: string | null
  tz_offset_hours?: number | null
}
export type PreviewResult =
  | { kind: 'scalar'; value: number | null; unit: string }
  | { kind: 'series'; points: { ts: string; value: number | null }[]; unit: string }

export interface VariableDependency {
  depends_on_type: 'tag' | 'variable'
  depends_on_tag_id: number | null
  depends_on_variable_id: number | null
}

export const listFacilityVariables = () => api.get<FacilityVariable[]>('/facility-variables/')
export const getFacilityVariable = (id: number) => api.get<FacilityVariable>(`/facility-variables/${id}`)
export const createFacilityVariable = (data: FacilityVariableCreate) =>
  api.post<FacilityVariable>('/facility-variables/', data)
export const updateFacilityVariable = (id: number, data: FacilityVariableUpdate) =>
  api.put<FacilityVariable>(`/facility-variables/${id}`, data)
export const deleteFacilityVariable = (id: number, force = false) =>
  api.delete(`/facility-variables/${id}${force ? '?force=true' : ''}`)
export const validateExpression = (body: { expression: ExprNode; kind: 'scalar' | 'series' }) =>
  api.post<{ valid: boolean }>('/facility-variables/validate', body)
export const previewVariable = (id: number, body: PreviewRequestBody) =>
  api.post<PreviewResult>(`/facility-variables/${id}/preview`, body)
export const getVariableDependencies = (id: number) =>
  api.get<VariableDependency[]>(`/facility-variables/${id}/dependencies`)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- facilityVariables.client`
Expected: PASS (6/6).

- [ ] **Step 5: Commit**

```bash
git add src/api/client.ts src/api/__tests__/facilityVariables.client.test.ts
git commit -m "feat(facility-vars-ui): facility-variable API client wrappers + types"
```

---

### Task 3: Management page (list) + route + sidebar + permission labels

**Files:**
- Create: `src/pages/FacilityVariables.tsx`
- Test: `src/pages/FacilityVariables.gating.test.tsx`
- Modify: `src/App.tsx` (route), `src/components/Layout.tsx` (nav item)
- Modify: `src/pages/Users.tsx` + `src/i18n/locales/*/users.json` (permission labels)

**Interfaces:**
- Consumes: `listFacilityVariables`, `deleteFacilityVariable`, `FacilityVariable` (Task 2); `facilityVariables` namespace (Task 1).
- Produces: a `FacilityVariables` default export rendering the list with a gated `+ Add Variable` button and per-row actions; later tasks (5/6) mount the editor modal here. Export a placeholder modal hook point: the page holds `const [showAdd, setShowAdd] = useState(false)` and `const [editVar, setEditVar] = useState<FacilityVariable | null>(null)` and renders `{showAdd && <VariableEditorModal onClose={…} />}` / `{editVar && <VariableEditorModal initial={editVar} onClose={…} />}` — `VariableEditorModal` is created in Task 5. For THIS task, stub it as a local component that returns `null` so the page compiles; Task 5 replaces the stub.

- [ ] **Step 1: Write the failing test**

`src/pages/FacilityVariables.gating.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../i18n'
import FacilityVariables from './FacilityVariables'

const canMock = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator', permissions: [] }, can: canMock, logout: vi.fn() }),
}))
vi.mock('../api/client', () => ({
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [] }),
  deleteFacilityVariable: vi.fn().mockResolvedValue({ data: {} }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('FacilityVariables create gating', () => {
  beforeEach(() => vi.clearAllMocks())
  it('hides add button when can() is false', async () => {
    await i18n.changeLanguage('en')
    canMock.mockReturnValue(false)
    wrap(<FacilityVariables />)
    expect(screen.queryByRole('button', { name: /Add Variable/i })).not.toBeInTheDocument()
  })
  it('shows add button when can(facility_variable:create) is true', async () => {
    await i18n.changeLanguage('en')
    canMock.mockImplementation((p: string) => p === 'facility_variable:create')
    wrap(<FacilityVariables />)
    expect(await screen.findByRole('button', { name: /Add Variable/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- FacilityVariables.gating`
Expected: FAIL — module `./FacilityVariables` not found.

- [ ] **Step 3: Create `src/pages/FacilityVariables.tsx`**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Variable } from 'lucide-react'
import { listFacilityVariables, deleteFacilityVariable } from '../api/client'
import type { FacilityVariable } from '../api/client'
import { useAuth } from '../context/AuthContext'

// Replaced by the real editor in Task 5. Stub keeps the page compiling.
function VariableEditorModal(_props: { initial?: FacilityVariable; onClose: () => void }) {
  return null
}

export default function FacilityVariables() {
  const { t } = useTranslation(['facilityVariables', 'common'])
  const { can } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editVar, setEditVar] = useState<FacilityVariable | null>(null)

  const { data: vars = [], isLoading } = useQuery({
    queryKey: ['facility-variables'],
    queryFn: () => listFacilityVariables().then((r) => r.data),
  })

  const delMut = useMutation({
    mutationFn: (v: FacilityVariable) => deleteFacilityVariable(v.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['facility-variables'] }),
  })

  const handleDeactivate = (v: FacilityVariable) => {
    if (!confirm(t('confirm_deactivate', { name: v.name }))) return
    delMut.mutate(v, {
      onError: (e) => {
        const status = (e as AxiosError)?.response?.status
        alert(status === 409 ? t('deactivate_blocked') : t('error_generic'))
      },
    })
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-2">
            <Variable className="w-5 h-5 text-emerald-400" /> {t('title')}
          </h1>
          <p className="text-sm text-gray-400">{t('subtitle')}</p>
        </div>
        {can('facility_variable:create') && (
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-sm hover:bg-emerald-600/30"
          >
            {t('add')}
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-gray-500">{t('common:loading')}</div>
      ) : vars.length === 0 ? (
        <div className="py-12 text-center text-gray-500">{t('empty')}</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-start border-b border-edge text-gray-400">
              <th className="text-start py-2">{t('col_code')}</th>
              <th className="text-start">{t('col_name')}</th>
              <th className="text-start">{t('col_kind')}</th>
              <th className="text-start">{t('col_unit')}</th>
              <th className="text-start">{t('col_deps')}</th>
              <th className="text-start">{t('col_status')}</th>
              <th className="text-end">{t('col_actions')}</th>
            </tr>
          </thead>
          <tbody>
            {vars.map((v) => (
              <tr key={v.id} className="border-b border-edge/50">
                <td className="py-2 font-mono text-cyan-300">{v.code}</td>
                <td className="text-gray-200">{v.name}</td>
                <td className="text-gray-400">{t(v.kind === 'scalar' ? 'kind_scalar' : 'kind_series')}</td>
                <td className="text-gray-400">{v.unit || '—'}</td>
                <td className="text-gray-400">{v.dependency_count}</td>
                <td>
                  <span className={v.is_active ? 'text-emerald-400' : 'text-gray-500'}>
                    {t(v.is_active ? 'status_active' : 'status_inactive')}
                  </span>
                </td>
                <td className="text-end space-x-2 whitespace-nowrap">
                  {can('facility_variable:edit') && (
                    <button onClick={() => setEditVar(v)} className="text-cyan-400 hover:underline">
                      {t('action_edit')}
                    </button>
                  )}
                  {can('facility_variable:delete') && v.is_active && (
                    <button onClick={() => handleDeactivate(v)} className="text-red-400 hover:underline">
                      {t('action_deactivate')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAdd && <VariableEditorModal onClose={() => setShowAdd(false)} />}
      {editVar && <VariableEditorModal initial={editVar} onClose={() => setEditVar(null)} />}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- FacilityVariables.gating`
Expected: PASS (2/2).

- [ ] **Step 5: Register the route in `src/App.tsx`**

Add the import alongside the other page imports:
```ts
import FacilityVariables from './pages/FacilityVariables'
```
Add the route inside the `<Route path="/" element={<…Layout…/>}>` block, next to `tags`:
```tsx
<Route path="facility-variables" element={<FacilityVariables />} />
```

- [ ] **Step 6: Add the sidebar nav item in `src/components/Layout.tsx`**

Import the icon (add to the existing lucide-react import): `Variable`. Append to the `nav` array:
```ts
{ to: '/facility-variables', labelKey: 'nav_facility_variables', icon: Variable, iconColor: 'text-emerald-400', iconActiveColor: 'text-emerald-300' },
```

- [ ] **Step 7: Add permission labels to `src/pages/Users.tsx` + 5 `users.json`**

In `Users.tsx`, extend `PERM_KEYS`:
```ts
  ['facility_variable:create', 'perm_fv_create'],
  ['facility_variable:edit', 'perm_fv_edit'],
  ['facility_variable:delete', 'perm_fv_delete'],
```
Add to all 5 `locales/*/users.json` (en shown; translate the rest):
```json
"perm_fv_create": "Create facility variables",
"perm_fv_edit": "Edit facility variables",
"perm_fv_delete": "Delete facility variables"
```

- [ ] **Step 8: Run full frontend test + typecheck**

Run: `pnpm test -- FacilityVariables.gating parity users` then `pnpm tsc --noEmit`
Expected: all PASS; tsc clean.

- [ ] **Step 9: Commit**

```bash
git add src/pages/FacilityVariables.tsx src/pages/FacilityVariables.gating.test.tsx src/App.tsx src/components/Layout.tsx src/pages/Users.tsx src/i18n/locales
git commit -m "feat(facility-vars-ui): management list page + route + sidebar + permission labels"
```

---

### Task 4: Expression builder component

**Files:**
- Create: `src/pages/facilityVariables/ExpressionBuilder.tsx`
- Test: `src/pages/facilityVariables/ExpressionBuilder.test.tsx`

**Interfaces:**
- Consumes: `ExprNode`, `FacilityVariable` (Task 2); `Tag` type + `getTags` (existing client). Tags + variables are passed in as props (the modal in Task 5 fetches them).
- Produces: `ExpressionBuilder` (default export) and a named `emptyNode(op)` factory.
  - Props: `{ value: ExprNode; onChange: (node: ExprNode) => void; tags: { id: number; name: string; unit?: string }[]; variables: { id: number; code: string }[] }`.
  - The component is a recursive block editor. Changing the op `<select>` swaps the node to `emptyNode(op)`. Each op renders its own fields; nodes with child nodes (`reduce`, `moving_avg`, `round`, `abs`, `add`, `sub`, `mul`, `div`, `coalesce`) recurse via the same component.

- [ ] **Step 1: Write the failing test**

`src/pages/facilityVariables/ExpressionBuilder.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import ExpressionBuilder, { emptyNode } from './ExpressionBuilder'

const tags = [{ id: 1, name: 'Debi', unit: 'm3' }]
const variables = [{ id: 9, code: 'var_x' }]

describe('ExpressionBuilder', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('emptyNode produces a valid const node', () => {
    expect(emptyNode('const')).toEqual({ op: 'const', value: 0 })
  })

  it('emits an agg node when op=agg and a tag is chosen', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder value={emptyNode('agg')} onChange={onChange} tags={tags} variables={variables} />)
    // choose the tag
    fireEvent.change(screen.getByLabelText(/Tag/i), { target: { value: '1' } })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ op: 'agg', source: { type: 'tag', tag_id: 1 }, agg: 'sum', window: 'day' }),
    )
  })

  it('switching op to const swaps the node', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilder value={emptyNode('agg')} onChange={onChange} tags={tags} variables={variables} />)
    fireEvent.change(screen.getByLabelText(/Operation/i), { target: { value: 'const' } })
    expect(onChange).toHaveBeenCalledWith({ op: 'const', value: 0 })
  })

  it('reduce node renders a nested child builder', () => {
    const node = { op: 'reduce', reduce: 'sum', source: { op: 'series', source: { type: 'tag', tag_id: 1 }, agg: 'sum', grain: 'day', window: 'day' } }
    render(<ExpressionBuilder value={node} onChange={vi.fn()} tags={tags} variables={variables} />)
    // two Operation selects: outer (reduce) + nested (series)
    expect(screen.getAllByLabelText(/Operation/i).length).toBe(2)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- ExpressionBuilder`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `src/pages/facilityVariables/ExpressionBuilder.tsx`**

```tsx
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { ExprNode } from '../../api/client'

const OPS = ['agg', 'series', 'const', 'ref', 'reduce', 'moving_avg', 'round', 'abs', 'add', 'sub', 'mul', 'div', 'coalesce'] as const
const AGGS = ['sum', 'avg', 'min', 'max', 'last', 'delta'] as const
const REDUCES = ['sum', 'avg', 'min', 'max', 'last'] as const
const GRAINS = ['hour', 'day', 'week', 'month'] as const
const ON_ZERO = ['null', 'zero', 'fail'] as const

type Op = (typeof OPS)[number]

export function emptyNode(op: Op): ExprNode {
  switch (op) {
    case 'const': return { op: 'const', value: 0 }
    case 'ref': return { op: 'ref', variable_id: 0 }
    case 'agg': return { op: 'agg', source: { type: 'tag', tag_id: 0 }, agg: 'sum', window: 'day' }
    case 'series': return { op: 'series', source: { type: 'tag', tag_id: 0 }, agg: 'sum', grain: 'day', window: 'day' }
    case 'reduce': return { op: 'reduce', reduce: 'sum', source: emptyNode('series') }
    case 'moving_avg': return { op: 'moving_avg', window_size: 3, source: emptyNode('series') }
    case 'round': return { op: 'round', ndigits: 0, source: emptyNode('agg') }
    case 'abs': return { op: 'abs', source: emptyNode('agg') }
    case 'div': return { op: 'div', on_zero: 'null', args: [emptyNode('agg'), emptyNode('const')] }
    default: return { op, args: [emptyNode('agg'), emptyNode('const')] } // add|sub|mul|coalesce
  }
}

const selCls = 'bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-sm text-white'

interface Props {
  value: ExprNode
  onChange: (node: ExprNode) => void
  tags: { id: number; name: string; unit?: string }[]
  variables: { id: number; code: string }[]
}

export default function ExpressionBuilder({ value, onChange, tags, variables }: Props) {
  const { t } = useTranslation('facilityVariables')
  const opId = useId()
  const node = value || emptyNode('const')
  const op = node.op as Op
  const patch = (p: Record<string, unknown>) => onChange({ ...node, ...p })
  const args = (node.args as ExprNode[]) || []
  const setArg = (i: number, child: ExprNode) => patch({ args: args.map((a, j) => (j === i ? child : a)) })

  return (
    <div className="border border-edge rounded-lg p-3 space-y-2 bg-black/20">
      <label className="flex items-center gap-2 text-xs text-gray-400">
        {t('builder_op')}
        <select id={opId} aria-label={t('builder_op')} className={selCls} value={op}
          onChange={(e) => onChange(emptyNode(e.target.value as Op))}>
          {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>

      {op === 'const' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_value')}
          <input type="number" className={selCls} value={Number(node.value ?? 0)}
            onChange={(e) => patch({ value: Number(e.target.value) })} />
        </label>
      )}

      {op === 'ref' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_variable')}
          <select className={selCls} value={Number(node.variable_id ?? 0)}
            onChange={(e) => patch({ variable_id: Number(e.target.value) })}>
            <option value={0}>—</option>
            {variables.map((v) => <option key={v.id} value={v.id}>{v.code}</option>)}
          </select>
        </label>
      )}

      {(op === 'agg' || op === 'series') && (
        <div className="flex flex-wrap gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_tag')}
            <select aria-label={t('builder_tag')} className={selCls}
              value={Number((node.source as { tag_id?: number })?.tag_id ?? 0)}
              onChange={(e) => patch({ source: { type: 'tag', tag_id: Number(e.target.value) } })}>
              <option value={0}>—</option>
              {tags.map((tg) => <option key={tg.id} value={tg.id}>{tg.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_agg')}
            <select className={selCls} value={String(node.agg ?? 'sum')}
              onChange={(e) => patch({ agg: e.target.value })}>
              {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          {op === 'series' && (
            <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_grain')}
              <select className={selCls} value={String(node.grain ?? 'day')}
                onChange={(e) => patch({ grain: e.target.value })}>
                {GRAINS.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
          )}
          <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_window')}
            <input className={selCls} value={String(node.window ?? 'day')}
              placeholder={t('builder_window_help')}
              onChange={(e) => patch({ window: e.target.value })} />
          </label>
        </div>
      )}

      {op === 'reduce' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_reduce')}
          <select className={selCls} value={String(node.reduce ?? 'sum')}
            onChange={(e) => patch({ reduce: e.target.value })}>
            {REDUCES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      )}

      {op === 'moving_avg' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_window_size')}
          <input type="number" min={1} className={selCls} value={Number(node.window_size ?? 3)}
            onChange={(e) => patch({ window_size: Math.max(1, Number(e.target.value)) })} />
        </label>
      )}

      {op === 'round' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_ndigits')}
          <input type="number" className={selCls} value={Number(node.ndigits ?? 0)}
            onChange={(e) => patch({ ndigits: Number(e.target.value) })} />
        </label>
      )}

      {op === 'div' && (
        <label className="flex items-center gap-2 text-xs text-gray-400">{t('builder_on_zero')}
          <select className={selCls} value={String(node.on_zero ?? 'null')}
            onChange={(e) => patch({ on_zero: e.target.value })}>
            {ON_ZERO.map((z) => <option key={z} value={z}>{z}</option>)}
          </select>
        </label>
      )}

      {/* single-child ops */}
      {(op === 'reduce' || op === 'moving_avg' || op === 'round' || op === 'abs') && (
        <div className="ms-4 border-s border-edge ps-3">
          <ExpressionBuilder value={node.source as ExprNode} tags={tags} variables={variables}
            onChange={(child) => patch({ source: child })} />
        </div>
      )}

      {/* variadic ops */}
      {(op === 'add' || op === 'sub' || op === 'mul' || op === 'div' || op === 'coalesce') && (
        <div className="ms-4 border-s border-edge ps-3 space-y-2">
          {args.map((a, i) => (
            <div key={i} className="space-y-1">
              <ExpressionBuilder value={a} tags={tags} variables={variables} onChange={(child) => setArg(i, child)} />
              {args.length > 1 && (
                <button type="button" className="text-xs text-red-400 hover:underline"
                  onClick={() => patch({ args: args.filter((_, j) => j !== i) })}>
                  {t('builder_remove')}
                </button>
              )}
            </div>
          ))}
          <button type="button" className="text-xs text-cyan-400 hover:underline"
            onClick={() => patch({ args: [...args, emptyNode('const')] })}>
            {t('builder_add_arg')}
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- ExpressionBuilder`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add src/pages/facilityVariables/ExpressionBuilder.tsx src/pages/facilityVariables/ExpressionBuilder.test.tsx
git commit -m "feat(facility-vars-ui): recursive block expression builder"
```

---

### Task 5: Create/Edit wizard modal (wires builder + basic info + save)

**Files:**
- Modify: `src/pages/FacilityVariables.tsx` (replace the `VariableEditorModal` stub with the real modal)
- Test: `src/pages/facilityVariables/VariableEditorModal.test.tsx`

> The modal lives in `FacilityVariables.tsx` (co-located like `Tags.tsx`'s modals). If the file grows past ~400 lines, extract `VariableEditorModal` into `src/pages/facilityVariables/VariableEditorModal.tsx` and import it — report this as a DONE_WITH_CONCERNS note rather than splitting silently mid-task.

**Interfaces:**
- Consumes: `ExpressionBuilder` + `emptyNode` (Task 4); `createFacilityVariable`, `updateFacilityVariable`, `FacilityVariable`, `FacilityVariableCreate`, `getTags`, `listFacilityVariables` (Tasks 2 + existing); `PreviewPanel` (Task 6 — for THIS task stub `PreviewPanel` as a local `() => null` and replace in Task 6).
- Props: `{ initial?: FacilityVariable; onClose: () => void }`.
- Behavior: stepper (basic → expression → window/grain → preview). On save: create (no `initial`) posts `FacilityVariableCreate`; edit (`initial` present) puts `FacilityVariableUpdate` (no `code`/`kind`). Invalidates `['facility-variables']`, calls `onClose` on success. Surfaces 409 (duplicate code) and 422 (`detail`) inline.

- [ ] **Step 1: Write the failing test**

`src/pages/facilityVariables/VariableEditorModal.test.tsx`:
```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import { VariableEditorModal } from '../FacilityVariables'

const createMock = vi.fn().mockResolvedValue({ data: { id: 1 } })
vi.mock('../../api/client', () => ({
  createFacilityVariable: (...a: unknown[]) => createMock(...a),
  updateFacilityVariable: vi.fn().mockResolvedValue({ data: {} }),
  getTags: vi.fn().mockResolvedValue({ data: [{ id: 1, name: 'Debi', unit: 'm3' }] }),
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [] }),
  validateExpression: vi.fn().mockResolvedValue({ data: { valid: true } }),
  previewVariable: vi.fn().mockResolvedValue({ data: { kind: 'scalar', value: 1, unit: 'm3' } }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VariableEditorModal', () => {
  beforeEach(async () => { await i18n.changeLanguage('en'); vi.clearAllMocks() })

  it('creates a scalar const variable', async () => {
    wrap(<VariableEditorModal onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/^Code$/i), { target: { value: 'v1' } })
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: 'V One' } })
    // advance to save (default expression is const 0 → valid scalar)
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))
    await waitFor(() => expect(createMock).toHaveBeenCalled())
    const body = createMock.mock.calls[0][0]
    expect(body).toMatchObject({ code: 'v1', name: 'V One', kind: 'scalar' })
    expect(body.expression).toBeTruthy()
  })
})
```
> The Save button must be reachable without stepping through every wizard page for the test — render Save on every step (disabled until `code`+`name` are non-empty), OR keep a single scrollable form. Choose the single-scrollable-form layout with labeled sections (simpler, fewer step-navigation bugs); the i18n step labels become section headers. This keeps `getByLabelText('Code')` and the Save button co-present.

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- VariableEditorModal`
Expected: FAIL — `VariableEditorModal` is not exported (currently a stub returning null / not exported).

- [ ] **Step 3: Replace the stub with the real modal (named export)**

In `src/pages/FacilityVariables.tsx`, replace the `VariableEditorModal` stub with the implementation below and export it (`export function VariableEditorModal`). Add the needed imports (`useState`, `useTranslation` already present; add `createFacilityVariable, updateFacilityVariable, getTags` and types; import `ExpressionBuilder, { emptyNode }`). Stub `PreviewPanel` locally as `function PreviewPanel(_: { variableId: number; kind: 'scalar' | 'series' }) { return null }` (Task 6 replaces it).

```tsx
export function VariableEditorModal({ initial, onClose }: { initial?: FacilityVariable; onClose: () => void }) {
  const { t } = useTranslation(['facilityVariables', 'common'])
  const qc = useQueryClient()
  const [code, setCode] = useState(initial?.code ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [kind, setKind] = useState<'scalar' | 'series'>(initial?.kind ?? 'scalar')
  const [unit, setUnit] = useState(initial?.unit ?? '')
  const [grain, setGrain] = useState(initial?.default_time_grain ?? 'day')
  const [expression, setExpression] = useState<ExprNode>(initial?.expression ?? emptyNode('const'))

  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => getTags().then((r) => r.data) })
  const { data: variables = [] } = useQuery({
    queryKey: ['facility-variables'],
    queryFn: () => listFacilityVariables().then((r) => r.data),
  })

  const mut = useMutation({
    mutationFn: () => {
      if (initial) {
        return updateFacilityVariable(initial.id, {
          name, description, unit, expression, default_time_grain: grain,
        }).then((r) => r.data)
      }
      return createFacilityVariable({
        code, name, description, kind, unit, expression, default_time_grain: grain,
      }).then((r) => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['facility-variables'] }); onClose() },
  })

  const errDetail = (mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail
  const status = (mut.error as AxiosError)?.response?.status
  const inputCls = 'w-full bg-surface-sunken border border-edge-strong rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl w-full max-w-2xl p-6 space-y-4 my-8">
        <h2 className="text-lg font-semibold text-white">{t(initial ? 'edit_title' : 'create_title')}</h2>

        <section className="space-y-2">
          <h3 className="text-xs uppercase text-gray-500">{t('step_basic')}</h3>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_code')}</span>
              <input aria-label={t('field_code')} className={inputCls} value={code} disabled={!!initial}
                onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_name')}</span>
              <input aria-label={t('field_name')} className={inputCls} value={name}
                onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_kind')}</span>
              <select className={inputCls} value={kind} disabled={!!initial}
                onChange={(e) => setKind(e.target.value as 'scalar' | 'series')}>
                <option value="scalar">{t('kind_scalar')}</option>
                <option value="series">{t('kind_series')}</option>
              </select>
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_unit')}</span>
              <input className={inputCls} value={unit} onChange={(e) => setUnit(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1 col-span-2">
              <span>{t('field_description')}</span>
              <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
            <label className="text-xs text-gray-400 space-y-1">
              <span>{t('field_grain')}</span>
              <select className={inputCls} value={grain ?? 'day'} onChange={(e) => setGrain(e.target.value)}>
                {['hour', 'day', 'week', 'month'].map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-xs uppercase text-gray-500">{t('step_expression')}</h3>
          <ExpressionBuilder value={expression} onChange={setExpression}
            tags={tags} variables={variables.map((v) => ({ id: v.id, code: v.code }))} />
        </section>

        {initial && (
          <section className="space-y-2">
            <h3 className="text-xs uppercase text-gray-500">{t('step_preview')}</h3>
            <PreviewPanel variableId={initial.id} kind={kind} />
          </section>
        )}

        {mut.isError && (
          <p className="text-red-400 text-sm">
            {status === 409 ? t('error_duplicate_code') : errDetail || t('error_generic')}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
            {t('common:cancel')}
          </button>
          <button onClick={() => mut.mutate()} disabled={mut.isPending || !code || !name}
            className="px-4 py-2 rounded-lg bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 text-sm disabled:opacity-40">
            {mut.isPending ? t('saving') : t('save')}
          </button>
        </div>
      </div>
    </div>
  )
}
```
Update the page body to use the named modal (remove the old stub; the `{showAdd && <VariableEditorModal …/>}` lines already match). Ensure `AxiosError` is imported (`import type { AxiosError } from 'axios'`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- VariableEditorModal FacilityVariables.gating`
Expected: PASS.

- [ ] **Step 5: Typecheck + commit**

Run: `pnpm tsc --noEmit` → clean.
```bash
git add src/pages/FacilityVariables.tsx src/pages/facilityVariables/VariableEditorModal.test.tsx
git commit -m "feat(facility-vars-ui): variable create/edit modal wiring builder + save"
```

---

### Task 6: Preview panel (validate + preview, scalar/series)

**Files:**
- Create: `src/pages/facilityVariables/PreviewPanel.tsx`
- Modify: `src/pages/FacilityVariables.tsx` (replace the local `PreviewPanel` stub with an import)
- Test: `src/pages/facilityVariables/PreviewPanel.test.tsx`

**Interfaces:**
- Consumes: `previewVariable`, `PreviewResult`, `PreviewRequestBody` (Task 2).
- Props: `{ variableId: number; kind: 'scalar' | 'series' }`.
- Behavior: a month picker (year + month inputs, defaulting to current values passed via props is NOT allowed — `Date.now()` is fine in the browser; default year/month from `new Date()`). On "Preview" click, POST preview; render scalar value or a series points count + a small recharts line (reuse the project's existing recharts usage in `Trend.tsx`; if importing recharts is heavy for the test, render the points count text and guard the chart with `points.length > 0`). Surface 422 `detail` inline.

- [ ] **Step 1: Write the failing test**

`src/pages/facilityVariables/PreviewPanel.test.tsx`:
```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../../i18n'
import PreviewPanel from './PreviewPanel'

const previewMock = vi.fn()
vi.mock('../../api/client', () => ({ previewVariable: (...a: unknown[]) => previewMock(...a) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('PreviewPanel', () => {
  beforeEach(async () => { await i18n.changeLanguage('en'); vi.clearAllMocks() })

  it('renders a scalar preview value', async () => {
    previewMock.mockResolvedValue({ data: { kind: 'scalar', value: 42.5, unit: 'm3' } })
    wrap(<PreviewPanel variableId={3} kind="scalar" />)
    fireEvent.click(screen.getByRole('button', { name: /Preview/i }))
    await waitFor(() => expect(previewMock).toHaveBeenCalledWith(3, expect.objectContaining({ window: expect.objectContaining({ type: 'month' }) })))
    expect(await screen.findByText(/42.5/)).toBeInTheDocument()
  })

  it('renders the series point count', async () => {
    previewMock.mockResolvedValue({ data: { kind: 'series', points: [{ ts: 'x', value: 1 }, { ts: 'y', value: 2 }], unit: 'm3' } })
    wrap(<PreviewPanel variableId={5} kind="series" />)
    fireEvent.click(screen.getByRole('button', { name: /Preview/i }))
    expect(await screen.findByText(/2 points/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- PreviewPanel`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `src/pages/facilityVariables/PreviewPanel.tsx`**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { previewVariable } from '../../api/client'
import type { PreviewResult } from '../../api/client'

export default function PreviewPanel({ variableId, kind }: { variableId: number; kind: 'scalar' | 'series' }) {
  const { t } = useTranslation('facilityVariables')
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const mut = useMutation({
    mutationFn: () => previewVariable(variableId, { window: { type: 'month', year, month } }).then((r) => r.data),
  })
  const result = mut.data as PreviewResult | undefined
  const errDetail = (mut.error as AxiosError<{ detail: string }>)?.response?.data?.detail
  const selCls = 'bg-surface-sunken border border-edge-strong rounded px-2 py-1 text-sm text-white w-24'

  return (
    <div className="border border-edge rounded-lg p-3 space-y-2 bg-black/20">
      <div className="flex items-end gap-3">
        <label className="text-xs text-gray-400 space-y-1"><span>{t('preview_year')}</span>
          <input type="number" className={selCls} value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </label>
        <label className="text-xs text-gray-400 space-y-1"><span>{t('preview_month')}</span>
          <input type="number" min={1} max={12} className={selCls} value={month}
            onChange={(e) => setMonth(Number(e.target.value))} />
        </label>
        <button onClick={() => mut.mutate()} disabled={mut.isPending}
          className="px-3 py-1.5 rounded bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 text-sm disabled:opacity-40">
          {t('preview')}
        </button>
      </div>

      {mut.isError && <p className="text-red-400 text-sm">{errDetail || t('error_generic')}</p>}

      {!result ? (
        <p className="text-xs text-gray-500">{t('preview_empty')}</p>
      ) : result.kind === 'scalar' ? (
        <p className="text-white text-sm">
          {t('preview_scalar')}: <span className="font-mono">{result.value ?? '—'}</span> {result.unit}
        </p>
      ) : (
        <p className="text-gray-300 text-sm">{t('preview_series_points', { count: result.points.length })}</p>
      )}
    </div>
  )
}
```
In `src/pages/FacilityVariables.tsx`, remove the local `PreviewPanel` stub and `import PreviewPanel from './facilityVariables/PreviewPanel'`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- PreviewPanel VariableEditorModal`
Expected: PASS.

- [ ] **Step 5: Typecheck + commit**

Run: `pnpm tsc --noEmit` → clean.
```bash
git add src/pages/facilityVariables/PreviewPanel.tsx src/pages/facilityVariables/PreviewPanel.test.tsx src/pages/FacilityVariables.tsx
git commit -m "feat(facility-vars-ui): variable preview panel (scalar value / series points)"
```

---

### Task 7: AdvancedReports — variable picker + preview count + archive variable_refs

**Files:**
- Modify: `src/api/client.ts` (`TemplateCreate` gains `variable_ids?: number[]`)
- Modify: `src/pages/AdvancedReports.tsx`
- Modify: `src/i18n/locales/*/advancedReports.json` (new keys: `variables_help`, `variables_selected`, `preview_variable_count`, `archive_vars`)
- Test: `src/pages/AdvancedReports.variables.test.tsx`

**Interfaces:**
- Consumes: `listFacilityVariables`, `FacilityVariable` (Task 2). The template `form` already spreads into the create/update payload, so adding `variable_ids` to `DEFAULT_FORM` + the `TemplateCreate` type is sufficient for it to be sent.

- [ ] **Step 1: Write the failing test**

`src/pages/AdvancedReports.variables.test.tsx` — render the `TemplateEditorModal` (export it from `AdvancedReports.tsx` if not already exported; if exporting is invasive, test the payload assembly by mounting the page's editor). Minimal deterministic test:
```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../i18n'
import { TemplateEditorModal } from './AdvancedReports'

const createMock = vi.fn().mockResolvedValue({ data: { id: 1 } })
vi.mock('../api/client', () => ({
  createTemplate: (...a: unknown[]) => createMock(...a),
  updateTemplate: vi.fn(),
  getTags: vi.fn().mockResolvedValue({ data: [{ id: 1, name: 'Debi' }] }),
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [{ id: 9, code: 'var_x', name: 'Var X', kind: 'scalar', is_active: true }] }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('AdvancedReports variable picker', () => {
  beforeEach(async () => { await i18n.changeLanguage('en'); vi.clearAllMocks() })
  it('includes selected variable_ids in the create payload', async () => {
    wrap(<TemplateEditorModal onClose={vi.fn()} />)
    // name the template
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'T' } })
    // select the variable pill
    fireEvent.click(screen.getByRole('button', { name: /var_x/i }))
    // also select a tag to pass the step-0 guard, then save
    fireEvent.click(screen.getByRole('button', { name: /Debi/i }))
    // advance/save (single Save action)
    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }))
    await waitFor(() => expect(createMock).toHaveBeenCalled())
    expect(createMock.mock.calls[0][0]).toMatchObject({ variable_ids: [9] })
  })
})
```
> If `TemplateEditorModal` is not currently exported or requires more props (e.g. `initial`), adapt: export it, and pass the minimal props its signature needs (read lines 79–134). The non-negotiable assertion: the create payload contains `variable_ids: [9]`. If the modal's stepper makes the Save button unreachable without navigating steps, drive the steps (click the Next button by its i18n label) until Save is present — keep the assertion intact.

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- AdvancedReports.variables`
Expected: FAIL — `variable_ids` absent from payload (and/or `var_x` pill not rendered).

- [ ] **Step 3: Add `variable_ids` to the type + form**

In `src/api/client.ts`, `TemplateCreate` interface — add after `tag_ids: number[]`:
```ts
  variable_ids?: number[]
```
In `src/pages/AdvancedReports.tsx`, `DEFAULT_FORM` — add after `tag_ids: []`:
```ts
  variable_ids: [],
```

- [ ] **Step 4: Add the variable picker + query + toggle in `TemplateEditorModal`**

Add the facility-variables query (after the tags query):
```ts
const { data: facilityVars = [] } = useQuery({
  queryKey: ['facility-variables'],
  queryFn: () => listFacilityVariables().then((r) => r.data),
})
```
Add the toggle (after `toggleTag`):
```ts
const toggleVariable = (id: number) =>
  set('variable_ids', form.variable_ids.includes(id)
    ? form.variable_ids.filter((x) => x !== id)
    : [...form.variable_ids, id])
```
Append a variable picker sub-section inside the `step === 0` block (after the tag picker, before the block's closing `</div>`):
```tsx
<div className="pt-3 border-t border-edge/50">
  <p className="text-sm text-gray-400">{t('variables_help')}</p>
  <div className="flex flex-wrap gap-2 mt-1">
    {facilityVars.filter((v) => v.is_active).map((v) => (
      <button key={v.id} type="button" onClick={() => toggleVariable(v.id)}
        className={`px-3 py-1 rounded-lg text-sm border transition-colors ${
          form.variable_ids.includes(v.id)
            ? 'border-emerald-500 bg-emerald-600/20 text-emerald-300'
            : 'border-edge-strong text-gray-400 hover:border-gray-500'}`}>
        {v.code}
      </button>
    ))}
  </div>
  <p className="text-xs text-gray-500 mt-1">{t('variables_selected', { value: form.variable_ids.length })}</p>
</div>
```
Add the preview count row (after the tag-count row in step 3):
```tsx
<div className="flex justify-between">
  <span className="text-gray-500">{t('preview_variable_count')}</span>
  <span className="text-white">{form.variable_ids.length}</span>
</div>
```
Import `listFacilityVariables` at the top. (The create/update mutation already spreads `form`, so no mutation change is needed.)

- [ ] **Step 5: Surface `variable_refs` on the archive row (ArchiveTab)**

The backend archive response already includes `variable_refs`. Add a lightweight display: in `ArchiveTab`'s row map, after the format/size cells, add a cell showing the count when present:
```tsx
<td className="text-gray-400">
  {Array.isArray((e as { variable_refs?: unknown[] }).variable_refs) && (e as { variable_refs?: unknown[] }).variable_refs!.length > 0
    ? t('archive_vars', { count: (e as { variable_refs?: unknown[] }).variable_refs!.length })
    : '—'}
</td>
```
Add a matching `<th>{t('archive_vars_col')}</th>` in the archive table header. (Cast is used because the generated `ArchiveEntryResponse` type lacks the field; do NOT edit generated files.)

- [ ] **Step 6: Add the new i18n keys to all 5 `advancedReports.json`**

en: `"variables_help": "Optionally include facility variables", "variables_selected": "{{value}} variables selected", "preview_variable_count": "Variables", "archive_vars": "{{count}} vars", "archive_vars_col": "Vars"`. tr: `"variables_help": "İsteğe bağlı tesis değişkenleri ekleyin", "variables_selected": "{{value}} değişken seçildi", "preview_variable_count": "Değişkenler", "archive_vars": "{{count}} değişken", "archive_vars_col": "Değişken"`. Translate ru/de/ar. (Keep `{{value}}`/`{{count}}` tokens identical.)

- [ ] **Step 7: Run tests + parity + typecheck**

Run: `pnpm test -- AdvancedReports.variables parity` then `pnpm tsc --noEmit`
Expected: PASS; clean.

- [ ] **Step 8: Commit**

```bash
git add src/api/client.ts src/pages/AdvancedReports.tsx src/pages/AdvancedReports.variables.test.tsx src/i18n/locales
git commit -m "feat(facility-vars-ui): advanced-report variable picker + archive variable_refs display"
```

---

### Task 8: ExcelTemplates helpers — MappingRow + toSavePayload

**Files:**
- Modify: `src/pages/excelTemplates.helpers.ts`
- Test: `src/pages/excelTemplates.helpers.test.ts` (create if absent; the repo already has `*.helpers.test.ts` precedent)

**Interfaces:**
- Produces: `MappingRow` with the variable-binding fields; `toSavePayload` includes them and keeps enabled variable rows (whose `tag_id` is null). Consumed by Task 9's UI.

- [ ] **Step 1: Write the failing test**

`src/pages/excelTemplates.helpers.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { toSavePayload } from './excelTemplates.helpers'
import type { MappingRow } from './excelTemplates.helpers'

const base: MappingRow = {
  col_letter: 'B', source_code: '', label: '', tag_id: null, agg: 'last', enabled: true,
  source_type: 'variable', variable_id: 9, write_mode: 'reduce', reduce_op: 'sum',
  target_mode: 'cell', target_cell: 'B3', variable_code_snapshot: null,
}

describe('toSavePayload — variable binding', () => {
  it('keeps an enabled variable row even when tag_id is null', () => {
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [base])
    expect(out.columns).toHaveLength(1)
    expect(out.columns[0]).toMatchObject({
      col_letter: 'B', tag_id: null, source_type: 'variable', variable_id: 9,
      write_mode: 'reduce', reduce_op: 'sum', target_mode: 'cell', target_cell: 'B3',
    })
  })
  it('nulls variable_id for a tag row and keeps tag_id', () => {
    const tagRow: MappingRow = { ...base, source_type: 'tag', tag_id: 5, variable_id: 9, write_mode: null, reduce_op: null, target_mode: 'column', target_cell: null }
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [tagRow])
    expect(out.columns[0]).toMatchObject({ tag_id: 5, source_type: 'tag', variable_id: null })
  })
  it('drops a disabled row', () => {
    const out = toSavePayload({ name: 't', sheet: 'S' } as never, [{ ...base, enabled: false }])
    expect(out.columns).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- excelTemplates.helpers`
Expected: FAIL — `MappingRow` lacks the new fields / `toSavePayload` drops the variable row.

- [ ] **Step 3: Extend `MappingRow` + `toSavePayload`**

In `src/pages/excelTemplates.helpers.ts`, add to the `MappingRow` interface (after `enabled: boolean`):
```ts
  source_type: 'tag' | 'variable'
  variable_id: number | null
  write_mode: 'series' | 'reduce' | null
  reduce_op: 'sum' | 'avg' | 'min' | 'max' | 'last' | null
  target_mode: 'column' | 'cell'
  target_cell: string | null
  variable_code_snapshot: string | null
```
Rewrite `toSavePayload`'s `columns` builder:
```ts
columns: rows
  .filter((r) => r.enabled && (r.tag_id != null || (r.source_type === 'variable' && r.variable_id != null)))
  .map((r) => ({
    col_letter: r.col_letter,
    tag_id: r.source_type === 'tag' ? r.tag_id : null,
    agg: r.agg,
    source_code: r.source_code,
    enabled: r.enabled,
    source_type: r.source_type,
    variable_id: r.source_type === 'variable' ? r.variable_id : null,
    write_mode: r.write_mode ?? null,
    reduce_op: r.reduce_op ?? null,
    target_mode: r.target_mode,
    target_cell: r.target_cell ?? null,
  })),
```

- [ ] **Step 4: Update the row-builder that constructs `MappingRow`s from server data**

Wherever `excelTemplates.helpers.ts` (or `ExcelTemplates.tsx`) builds `MappingRow`s from the loaded template (the function that maps server columns → rows), default the new fields so existing tag rows are well-formed: `source_type: col.source_type ?? 'tag'`, `variable_id: col.variable_id ?? null`, `write_mode: col.write_mode ?? null`, `reduce_op: col.reduce_op ?? null`, `target_mode: col.target_mode ?? 'column'`, `target_cell: col.target_cell ?? null`, `variable_code_snapshot: col.variable_code_snapshot ?? null`. If that builder is a pure helper, add a test asserting the defaults; if it is inline in the component, Task 9 covers it.

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm test -- excelTemplates.helpers`
Expected: PASS (3/3).

- [ ] **Step 6: Commit**

```bash
git add src/pages/excelTemplates.helpers.ts src/pages/excelTemplates.helpers.test.ts
git commit -m "feat(facility-vars-ui): excel column variable-binding in MappingRow + toSavePayload"
```

---

### Task 9: ExcelTemplates column editor UI (variable-binding controls)

**Files:**
- Modify: `src/pages/ExcelTemplates.tsx`
- Modify: `src/i18n/locales/*/excelTemplates.json` (new keys)
- Test: `src/pages/ExcelTemplates.binding.test.tsx`

**Interfaces:**
- Consumes: `MappingRow` (Task 8), `listFacilityVariables` (Task 2).
- Produces: per-column controls for `source_type`, a variable picker (when `source_type==='variable'`), `write_mode`, `reduce_op` (when `write_mode==='reduce'`), and `target_mode`/`target_cell`.

- [ ] **Step 1: Write the failing test**

`src/pages/ExcelTemplates.binding.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import i18n from '../i18n'
import ExcelTemplates from './ExcelTemplates'

vi.mock('../api/client', () => ({
  listFacilityVariables: vi.fn().mockResolvedValue({ data: [{ id: 9, code: 'var_x', is_active: true }] }),
}))
// ExcelTemplates uses raw fetch for its own endpoints; stub global fetch to return one template with one column.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      String(url).includes('excel-templates')
        ? [{ name: 'T', sheet: 'S', columns: [{ col_letter: 'B', label: 'L', source_code: '', tag_id: 1, agg: 'last', enabled: true, source_type: 'tag' }] }]
        : [],
  })) as unknown as typeof fetch)
})

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ExcelTemplates variable binding UI', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })
  it('switching a column to variable source reveals the variable picker', async () => {
    wrap(<ExcelTemplates />)
    // open the template (click its name/row) — adapt selector to the page's open affordance
    const sourceSel = await screen.findByLabelText(/Source type/i)
    fireEvent.change(sourceSel, { target: { value: 'variable' } })
    expect(await screen.findByLabelText(/Variable/i)).toBeInTheDocument()
  })
})
```
> Adapt the "open the template" interaction to the page's actual affordance (read `ExcelTemplates.tsx` lines 70–160 to see how a template is selected into the editor view). The non-negotiable assertion: choosing `source_type='variable'` reveals a variable picker control. If the page requires selecting a template before the column table renders, drive that click first.

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- ExcelTemplates.binding`
Expected: FAIL — no "Source type" control exists.

- [ ] **Step 3: Add the column controls + variable query**

Read `ExcelTemplates.tsx` to find the row-setter helper (the `setRows` updater used by `tag_id`/`agg`/`enabled`). Add a facility-variables query near the templates query:
```ts
const { data: facilityVars = [] } = useQuery({
  queryKey: ['facility-variables'],
  queryFn: () => listFacilityVariables().then((r) => r.data),
})
```
Add header `<th>` cells after `map_enabled`: `{t('map_source_type')}`, `{t('map_variable')}`, `{t('map_write_mode')}`, `{t('map_reduce_op')}`, `{t('map_target_cell')}`.
Add the per-row `<td>` cells after the enabled checkbox. Use a row updater `update(col_letter, patch)`:
```tsx
<td>
  <select aria-label={t('map_source_type')} value={r.source_type}
    onChange={(e) => update(r.col_letter, { source_type: e.target.value as 'tag' | 'variable' })}>
    <option value="tag">tag</option>
    <option value="variable">variable</option>
  </select>
</td>
<td>
  {r.source_type === 'variable' ? (
    <select aria-label={t('map_variable')} value={r.variable_id ?? 0}
      onChange={(e) => update(r.col_letter, { variable_id: Number(e.target.value) || null })}>
      <option value={0}>—</option>
      {facilityVars.filter((v) => v.is_active).map((v) => <option key={v.id} value={v.id}>{v.code}</option>)}
    </select>
  ) : <span className="text-gray-600">—</span>}
</td>
<td>
  {r.source_type === 'variable' ? (
    <select aria-label={t('map_write_mode')} value={r.write_mode ?? 'series'}
      onChange={(e) => update(r.col_letter, { write_mode: e.target.value as 'series' | 'reduce' })}>
      <option value="series">series</option>
      <option value="reduce">reduce</option>
    </select>
  ) : <span className="text-gray-600">—</span>}
</td>
<td>
  {r.source_type === 'variable' && r.write_mode === 'reduce' ? (
    <select aria-label={t('map_reduce_op')} value={r.reduce_op ?? 'sum'}
      onChange={(e) => update(r.col_letter, { reduce_op: e.target.value as MappingRow['reduce_op'] })}>
      {['sum', 'avg', 'min', 'max', 'last'].map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  ) : <span className="text-gray-600">—</span>}
</td>
<td>
  {r.source_type === 'variable' ? (
    <div className="flex items-center gap-1">
      <select aria-label={t('map_target_mode')} value={r.target_mode}
        onChange={(e) => update(r.col_letter, { target_mode: e.target.value as 'column' | 'cell' })}>
        <option value="column">column</option>
        <option value="cell">cell</option>
      </select>
      {r.target_mode === 'cell' && (
        <input aria-label={t('map_target_cell')} className="w-16" value={r.target_cell ?? ''}
          onChange={(e) => update(r.col_letter, { target_cell: e.target.value || null })} />
      )}
    </div>
  ) : <span className="text-gray-600">—</span>}
</td>
```
If a generic `update(col_letter, patch)` helper does not exist, add one mirroring the existing per-field `setRows` updaters:
```ts
const update = (col: string, patch: Partial<MappingRow>) =>
  setRows((rs) => rs.map((r) => (r.col_letter === col ? { ...r, ...patch } : r)))
```
Import `listFacilityVariables` and the `MappingRow` type.

- [ ] **Step 4: Add the new i18n keys to all 5 `excelTemplates.json`**

en: `"map_source_type": "Source type", "map_variable": "Variable", "map_write_mode": "Write mode", "map_reduce_op": "Reduce", "map_target_mode": "Target", "map_target_cell": "Cell"`. tr: `"map_source_type": "Kaynak türü", "map_variable": "Değişken", "map_write_mode": "Yazma modu", "map_reduce_op": "İndirgeme", "map_target_mode": "Hedef", "map_target_cell": "Hücre"`. Translate ru/de/ar.

- [ ] **Step 5: Run tests + parity + typecheck**

Run: `pnpm test -- ExcelTemplates.binding excelTemplates.helpers parity` then `pnpm tsc --noEmit`
Expected: PASS; clean.

- [ ] **Step 6: Commit**

```bash
git add src/pages/ExcelTemplates.tsx src/pages/ExcelTemplates.binding.test.tsx src/i18n/locales
git commit -m "feat(facility-vars-ui): excel column variable-binding editor controls"
```

---

## Final Verification (run after all tasks)

```bash
cd scada-reporter/frontend
pnpm test                 # full Vitest suite — all green incl. parity
pnpm tsc --noEmit         # type-clean
pnpm exec prettier --check src   # format-clean (or `pnpm format`)
```
Expected: full suite green, tsc clean, prettier clean. Manual smoke (optional, backend running): create a scalar `const` variable, preview it, attach it to an advanced-report template, bind an Excel column to it.

---

## Self-Review (author checklist — completed)

**1. Spec coverage (design §445-495 UI Design + Phases 4/5/6):**
- List screen (code/name/kind/unit/dep-count/status/updated + edit/duplicate/deactivate/preview) → Task 3 (+ preview via Task 6; duplicate is a Minor — see note).
- Create/edit wizard (basic/source/op/window/preview/save) → Tasks 5 (single-form sections) + 4 (builder) + 6 (preview).
- Block-based expression builder (not free text) → Task 4 (recursive blocks; emits JSON, no free-text editor).
- Excel mapping UX (source_type/picker/write_mode/reduce_op/target_mode+cell) → Tasks 8 (logic) + 9 (UI).
- Advanced reports select facility variables → Task 7.
- Permission gating + human labels (×5) → Task 3 (Users PERM_KEYS + users.json).
- **Out of scope (correctly deferred):** dependency DAG graph (design §276 says v1 ships flat list — and the list page shows `dependency_count`; the full graph is a later UI upgrade); "duplicate" action (a convenience — implement as a Minor in Task 3 if cheap, else defer; not load-bearing).

**2. Placeholder scan:** No TBD/TODO. Each code step carries complete code. The three adaptive spots (Task 7 `TemplateEditorModal` export/props, Task 9 template-open affordance, Task 8 row-builder location) give an explicit decision rule + the non-negotiable assertion, not a vague "handle it".

**3. Type consistency:** `FacilityVariable`/`FacilityVariableCreate`/`PreviewResult`/`ExprNode` defined once (Task 2) and imported everywhere. `MappingRow` fields (Task 8) match the Task 9 controls and the backend `ColumnIn`. Query key `['facility-variables']` identical across Tasks 3/5/7/9. i18n namespace `facilityVariables` registered once (Task 1), consumed by Tasks 3/4/5/6.

---

## Execution Handoff

Recommended: **subagent-driven-development** — one fresh subagent per task, two-stage review between tasks, matching Plans 1-3. Ledger under a Plan-4 section in `.superpowers/sdd/progress.md`, briefs/reports namespaced, review packages SHA-named. Base before Task 1: current `master` HEAD.
