# Arabic (ar) UI Language + Full RTL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Arabic (`ar`) as a fifth UI language with RTL layout support (scoped to the Layout shell + structural fixes), and localize Excel/PDF reports into Arabic.

**Architecture:** Frontend adds an `ar` locale set (11 namespaces) + registers it in i18n; a direction helper sets `<html dir>` on language change; the Layout shell is mirrored for RTL. Backend widens the language literal and adds an Arabic report-label set. Parity tests (frontend + backend) are extended to cover `ar`.

**Tech Stack:** React 19 + Vite + Tailwind CSS v4 + react-i18next + Vitest; FastAPI + Pydantic + pytest.

## Global Constraints

- New language code: `ar`. Display label: `العربية`. Direction: `rtl`.
- Arabic translations are AI-generated drafts (flag for native review); the parity tests guarantee structural completeness, not linguistic quality.
- Every `ar/<ns>.json` MUST have a key set and `{{placeholder}}` set identical to the corresponding `en/<ns>.json` — enforced by `parity.test.ts`.
- The eleven namespaces: `common, login, settings, dashboard, tags, trend, reports, advancedReports, plc, metrics, users`.
- RTL scope: set `dir`/`lang` on `<html>` + mirror the **Layout shell only** (sidebar side, mobile drawer slide direction, directional borders/positioning). Do NOT pixel-mirror other pages.
- en/tr/ru/de must remain visually unchanged (they resolve to `dir="ltr"`).
- `User.language` is `String(5)` — `ar` fits, no DB migration.
- Backend tests run from `scada-reporter/backend` with the venv: `.venv/Scripts/python.exe -m pytest ...`. Frontend tests from `scada-reporter/frontend`: `pnpm test`; type-check `pnpm exec tsc --noEmit`; i18n guard `pnpm run lint:i18n`.

---

### Task 1: Backend Arabic support (language literal + report labels)

**Files:**
- Modify: `scada-reporter/backend/app/api/auth.py` (UserUpdate language literal)
- Modify: `scada-reporter/backend/app/i18n/report_labels.py` (add `ar` set + docstring)
- Modify: `scada-reporter/backend/tests/test_report_labels.py` (cover `ar`)
- Test: `scada-reporter/backend/tests/test_auth_me.py` (accept `ar`)

**Interfaces:**
- Produces: `get_labels("ar")` returns a full Arabic label dict (same keys as `en`); `UserUpdate(language="ar")` validates; `PATCH /auth/me {"language":"ar"}` persists.

- [ ] **Step 1: Write the failing backend label test**

In `scada-reporter/backend/tests/test_report_labels.py`, add `'ar'` to the loop in `test_all_languages_have_same_keys` and add a new test:

```python
def test_arabic_labels():
    labels = get_labels("ar")
    assert labels["summary_sheet"] == "ملخص"
    assert labels["total_reads"] == "إجمالي القراءات"
```

And change:
```python
def test_all_languages_have_same_keys():
    en_keys = set(get_labels("en").keys())
    for lang in ("tr", "ru", "de", "ar"):
        assert set(get_labels(lang).keys()) == en_keys, f"{lang} key mismatch"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /c/project/smart/scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_report_labels.py -v`
Expected: FAIL — `ar key mismatch` (ar absent) and `test_arabic_labels` KeyError/fallback returns English.

- [ ] **Step 3: Add the Arabic label set**

In `scada-reporter/backend/app/i18n/report_labels.py`, update the docstring language line to include `ar (Arabic)`, and add this `"ar"` entry to the `LABELS` dict (keys MUST exactly match the `en` set):

```python
    "ar": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "ملخص",
        "raw_sheet": "البيانات الخام",
        "statistics": "الإحصائيات",
        "percentiles": "المئينات",
        "anomalies": "الحالات الشاذة",
        "period_summary": "ملخص الفترة",
        "summary_stats": "إحصائيات موجزة",
        "system_health_summary": "ملخص صحة النظام",
        "chart": "رسم بياني",
        # ── Stat-block / column headers ──────────────────────────────────────
        "tag": "الوسم",
        "unit": "الوحدة",
        "total_reads": "إجمالي القراءات",
        "good_quality": "جودة جيدة",
        "availability_pct": "التوفر %",
        "average": "المتوسط",
        "std_dev": "الانحراف المعياري",
        "std": "الانحراف",
        "minimum": "الأدنى",
        "maximum": "الأقصى",
        "trend": "الاتجاه",
        "trend_slope": "ميل الاتجاه (وحدة/ساعة)",
        "trend_r2": "R²",
        "anomaly_count": "عدد الحالات الشاذة",
        "gap_count": "عدد الفجوات",
        "gap_total_seconds": "إجمالي الفجوة (ث)",
        "gap": "فجوة",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "الفترة",
        "count": "العدد",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "البداية",
        "end_label": "النهاية",
        "interval_label": "الفاصل الزمني",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "الوقت",
        "value": "القيمة",
        "type": "النوع",
        "severity": "الخطورة",
        "detail": "التفاصيل",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "الجودة",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "تقرير",
        "period_meta": "الفترة",
        "generated_at": "تم الإنشاء في",
        "format_label": "التنسيق",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "إجمالي الحالات الشاذة",
        "avg_availability": "متوسط التوفر",
        "tag_count": "عدد الوسوم",
        "top_10_anomalies": "أعلى 10 حالات شاذة",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "صفحة",
    },
```

NOTE: if the `en` set has more/fewer keys than the block above when you implement, mirror the EXACT `en` key list — the `test_all_languages_have_same_keys` test is the gate. Add any missing key with a sensible Arabic value; do not leave a key out.

- [ ] **Step 4: Run the label test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report_labels.py -v`
Expected: PASS (key parity for ar + `test_arabic_labels`).

- [ ] **Step 5: Write the failing auth language test**

In `scada-reporter/backend/tests/test_auth_me.py`, add (mirror the existing `operator` fixture pattern in that file):

```python
@pytest.mark.asyncio
async def test_self_language_change_to_arabic(client, operator, db_session):
    resp = await client.patch("/api/auth/me", json={"language": "ar"})
    assert resp.status_code == 200
    assert resp.json()["language"] == "ar"
    await db_session.refresh(operator)
    assert operator.language == "ar"
```

- [ ] **Step 6: Run it — expect FAIL (422, ar not in literal)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth_me.py::test_self_language_change_to_arabic -v`
Expected: FAIL — 422 (Pydantic rejects `"ar"`).

- [ ] **Step 7: Widen the language literal**

In `scada-reporter/backend/app/api/auth.py`, change `UserUpdate.language`:
```python
    language: Literal["en", "tr", "ru", "de", "ar"] | None = None
```

- [ ] **Step 8: Run the auth test + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth_me.py tests/test_report_labels.py -v` then `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 9: Commit**

```bash
git add scada-reporter/backend/app/api/auth.py scada-reporter/backend/app/i18n/report_labels.py scada-reporter/backend/tests/test_report_labels.py scada-reporter/backend/tests/test_auth_me.py
git commit -m "feat(i18n): backend Arabic support — report labels + language literal"
```

---

### Task 2: Frontend Arabic locale files + registration

**Files:**
- Create: `scada-reporter/frontend/src/i18n/locales/ar/<ns>.json` for all 11 namespaces
- Modify: `scada-reporter/frontend/src/i18n/index.ts` (SUPPORTED_LANGS + ar resources)
- Modify: `scada-reporter/frontend/src/components/LanguageSelector.tsx` (ar label)
- Modify: `scada-reporter/frontend/src/i18n/parity.test.ts` (cover ar)

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `SUPPORTED_LANGS` includes `'ar'`; `ar` resources registered; LanguageSelector shows `العربية`; parity test green for ar.

- [ ] **Step 1: Extend the parity test to cover `ar` (this is the failing test)**

In `scada-reporter/frontend/src/i18n/parity.test.ts`:
- Add `ar` imports for all eleven namespaces (mirror the existing `en*` import block), e.g. `import arCommon from './locales/ar/common.json'` … through `arUsers`.
- Add `ar: arX` to each entry of the `NAMESPACES` map.
- Add `'ar'` to `TARGET_LANGS`: `const TARGET_LANGS = ['tr', 'ru', 'de', 'ar'] as const`.

- [ ] **Step 2: Run it — expect FAIL (ar files missing → import error)**

Run: `cd /c/project/smart/scada-reporter/frontend && pnpm test -- src/i18n/parity.test.ts`
Expected: FAIL — cannot resolve `./locales/ar/common.json` (files not created yet).

- [ ] **Step 3: Create the 11 Arabic locale files**

For each namespace `<ns>` in `common, login, settings, dashboard, tags, trend, reports, advancedReports, plc, metrics, users`:
- Read `src/i18n/locales/en/<ns>.json`.
- Create `src/i18n/locales/ar/<ns>.json` with the EXACT same key structure (including nested objects) and the SAME `{{placeholder}}` tokens in each value, translating each English value into Modern Standard Arabic. Do not add, remove, or rename any key. Do not translate placeholder tokens (`{{count}}` stays `{{count}}`). Keep non-translatable tokens (units, `R²`, product name "EKONT SMART REPORT", numbers) as-is.
- For the `common` namespace, ensure `nav_users` and all `nav_*` keys are translated, and `language` (the selector aria-label) is translated.

Translation quality: Modern Standard Arabic, concise UI register. These are AI drafts (per Global Constraints).

- [ ] **Step 4: Register `ar` in i18n**

In `src/i18n/index.ts`:
- Add `'ar'` to `SUPPORTED_LANGS`: `export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de', 'ar'] as const`.
- Add imports for all eleven `ar*` JSONs (mirror the existing import blocks).
- Add an `ar: { common: arCommon, login: arLogin, settings: arSettings, dashboard: arDashboard, tags: arTags, trend: arTrend, reports: arReports, advancedReports: arAdvancedReports, plc: arPlc, metrics: arMetrics, users: arUsers }` entry to the `resources` object.
- Do NOT change the `ns` array (namespaces are language-independent).

- [ ] **Step 5: Add the selector label**

In `src/components/LanguageSelector.tsx`, extend `LABELS`:
```tsx
const LABELS: Record<Lang, string> = { en: 'English', tr: 'Türkçe', ru: 'Русский', de: 'Deutsch', ar: 'العربية' }
```

- [ ] **Step 6: Run parity + type-check + i18n guard**

Run:
```
pnpm test -- src/i18n/parity.test.ts
pnpm exec tsc --noEmit
pnpm run lint:i18n
```
Expected: parity PASS for ar (key + placeholder), tsc clean (the `Lang` union now includes `ar`; `LABELS: Record<Lang,string>` requires the ar entry — present), i18n guard PASS.

- [ ] **Step 7: Run the full frontend suite**

Run: `pnpm test`
Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/i18n/locales/ar/ scada-reporter/frontend/src/i18n/index.ts scada-reporter/frontend/src/i18n/parity.test.ts scada-reporter/frontend/src/components/LanguageSelector.tsx
git commit -m "feat(i18n): Arabic locale files + registration + selector label"
```

---

### Task 3: RTL direction handling

**Files:**
- Modify: `scada-reporter/frontend/src/i18n/index.ts` (dir helper + apply on change/init)
- Test: `scada-reporter/frontend/src/i18n/direction.test.ts` (new)

**Interfaces:**
- Consumes: `SUPPORTED_LANGS`/`Lang` from Task 2.
- Produces: exported `RTL_LANGS: Set<string>` and `dirFor(lang: string): 'rtl' | 'ltr'`; side effect — `document.documentElement.dir` / `.lang` update on language change and at init.

- [ ] **Step 1: Write the failing direction test**

Create `scada-reporter/frontend/src/i18n/direction.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import i18n, { dirFor } from './index'

describe('dirFor', () => {
  it('returns rtl for Arabic', () => {
    expect(dirFor('ar')).toBe('rtl')
  })
  it('returns ltr for en/tr/ru/de', () => {
    for (const l of ['en', 'tr', 'ru', 'de']) expect(dirFor(l)).toBe('ltr')
  })
})

describe('document direction follows language', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('sets <html dir=rtl lang=ar> when switching to Arabic', async () => {
    await i18n.changeLanguage('ar')
    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('ar')
  })

  it('reverts to ltr when switching back to English', async () => {
    await i18n.changeLanguage('ar')
    await i18n.changeLanguage('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.documentElement.lang).toBe('en')
  })
})
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `pnpm test -- src/i18n/direction.test.ts`
Expected: FAIL — `dirFor` is not exported / `document.documentElement.dir` not updated.

- [ ] **Step 3: Implement the direction helper + side effects**

In `src/i18n/index.ts`:
- Add near the top (after `SUPPORTED_LANGS`):
```ts
export const RTL_LANGS = new Set<string>(['ar'])
export function dirFor(lang: string): 'rtl' | 'ltr' {
  return RTL_LANGS.has(lang) ? 'rtl' : 'ltr'
}
function applyDir(lng: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lng
    document.documentElement.dir = dirFor(lng)
  }
}
```
- In the existing `i18n.on('languageChanged', (lng) => { ... })` handler, add `applyDir(lng)` alongside the `localStorage.setItem('lang', lng)` call.
- After `i18n.use(initReactI18next).init({...})` (or right after computing `initialLng`), call `applyDir(initialLng)` once so the initial page load has the correct direction.

- [ ] **Step 4: Run the direction test to verify it passes**

Run: `pnpm test -- src/i18n/direction.test.ts`
Expected: PASS (4 assertions).

- [ ] **Step 5: Type-check + full suite**

Run: `pnpm exec tsc --noEmit` then `pnpm test`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/frontend/src/i18n/index.ts scada-reporter/frontend/src/i18n/direction.test.ts
git commit -m "feat(i18n): RTL direction — set html dir/lang from language (ar=rtl)"
```

---

### Task 4: Layout shell RTL mirroring

**Files:**
- Modify: `scada-reporter/frontend/src/components/Layout.tsx`
- Test: `scada-reporter/frontend/src/components/Layout.rtl.test.tsx` (new)

**Interfaces:**
- Consumes: `dir` set by Task 3 (via `<html dir>`); Tailwind v4 logical utilities + `rtl:`/`ltr:` variants.
- Produces: a Layout whose sidebar/drawer mirror correctly under RTL while remaining identical under LTR.

**Context for the implementer:** `Layout.tsx` currently uses physical
utilities for the sidebar shell:
- `<aside>` is `w-56 ... border-r border-gray-800 ... fixed md:static inset-y-0 left-0 z-40 transform transition-transform ... ${mobileNav ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`.
- The mobile backdrop and top bar use direction-agnostic utilities.
Convert ONLY the directional ones so the sidebar sits on the inline-start
edge in both directions and the mobile drawer slides in from the correct
edge:
- `border-r` → `border-e` (logical inline-end border on the sidebar's content edge — verify visually; the sidebar border should be on the side facing the main content).
- `left-0` → `start-0` (logical inline-start) — Tailwind v4 supports `start-0`/`end-0` (CSS `inset-inline-start`).
- The hidden-state transform `-translate-x-full` flips sign under RTL. Use a direction-aware variant: keep `-translate-x-full` for LTR and add `rtl:translate-x-full` so under RTL the drawer hides off the right edge. The shown state `translate-x-0` and `md:translate-x-0` are direction-neutral and stay.
- Leave `gap-*`, `space-y-*`, padding that is symmetric, and icon markup unchanged.

Do not change any other page. Keep all text via `t(...)` (the i18n guard runs in lint).

- [ ] **Step 1: Write the failing RTL layout test**

Create `scada-reporter/frontend/src/components/Layout.rtl.test.tsx`. The goal: assert the sidebar uses direction-aware classes (so a regression to hardcoded `left-0`/`border-r`-only is caught). Mock `useAuth` and render within a router.

```tsx
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import Layout from './Layout'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'admin', role: 'admin', full_name: 'Admin' }, logout: vi.fn() }),
}))

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  )
}

describe('Layout RTL-aware sidebar', () => {
  it('sidebar uses logical/direction-aware utilities (not hardcoded left/border-r)', () => {
    const { container } = renderLayout()
    const aside = container.querySelector('aside')!
    expect(aside).toBeTruthy()
    const cls = aside.className
    // Logical inline-start positioning and direction-aware hidden transform
    expect(cls).toMatch(/(^|\s)start-0(\s|$)/)
    expect(cls).toContain('rtl:translate-x-full')
    // Must not reuse the physical left-0 anchor that breaks RTL
    expect(cls).not.toMatch(/(^|\s)left-0(\s|$)/)
  })
})
```

(Adjust the exact asserted tokens to match the final class strings you write in Step 3 — but the test MUST fail before the change and pass after, and must encode the RTL-awareness, not merely render.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `pnpm test -- src/components/Layout.rtl.test.tsx`
Expected: FAIL — current `aside` has `left-0` and no `start-0`/`rtl:translate-x-full`.

- [ ] **Step 3: Apply the RTL-aware Layout changes**

In `src/components/Layout.tsx`, edit the `<aside>` className per the Context above:
- Replace `border-r` with `border-e`.
- Replace `left-0` with `start-0`.
- Change the hidden-state expression so it includes `rtl:translate-x-full` in addition to `-translate-x-full`, e.g.:
  `${mobileNav ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full'} md:translate-x-0`
Leave everything else unchanged.

- [ ] **Step 4: Run the RTL test + full suite + tsc + i18n guard**

Run:
```
pnpm test -- src/components/Layout.rtl.test.tsx
pnpm test
pnpm exec tsc --noEmit
pnpm run lint:i18n
```
Expected: all PASS.

- [ ] **Step 5: Manual verification note (no code)**

After this task, a manual check (not automated) is recommended: run the app, switch to Arabic, confirm the sidebar moves to the right, the mobile drawer slides from the right, and text reads right-to-left. Record the result when verifying the branch; this step has no commit.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/frontend/src/components/Layout.tsx scada-reporter/frontend/src/components/Layout.rtl.test.tsx
git commit -m "feat(i18n): RTL-aware Layout shell (sidebar/drawer mirror under rtl)"
```

---

## Self-Review

**Spec coverage:**
- Frontend i18n registration (SUPPORTED_LANGS, 11 ar files, resources, selector label) → Task 2.
- RTL direction (`dir`/`lang` on html, dirFor) → Task 3.
- Layout structural RTL fixes → Task 4.
- Backend language literal + Arabic report labels → Task 1.
- Parity coverage for ar (frontend parity.test.ts + backend test_report_labels) → Tasks 2 and 1.
- Auth accepts `ar` → Task 1.
- Out-of-scope (per-page mirroring, numerals/calendar, native review) → not implemented, matches spec.

**Placeholder scan:** No TBD/TODO. The frontend Arabic string VALUES are produced at implementation time by translating each `en/<ns>.json`; the method, constraints (identical keys + placeholders), and the parity-test gate are fully specified. The backend Arabic label values are provided verbatim. Task 4's exact asserted class tokens are allowed to be adjusted to match the final classes, with the RED-before/GREEN-after requirement stated.

**Type consistency:** `dirFor`/`RTL_LANGS`/`applyDir` names are consistent between Task 3's implementation and test. `SUPPORTED_LANGS`/`Lang`/`LABELS` widening is consistent across Tasks 2–3. Backend `get_labels`/`LABELS["ar"]` and `UserUpdate.language` literal are consistent within Task 1.

**Ordering note:** Task 2 must precede Task 3 (Task 3's test imports the configured i18n and switches to `ar`, which requires the `ar` resources to exist) and Task 4 (RTL is meaningful once `ar` exists). Task 1 (backend) is independent and may run any time. Recommended order: 1, 2, 3, 4.
