# Arabic (ar) UI Language + Full RTL — Design

**Date:** 2026-06-17
**Status:** Approved (design), implementation plan pending
**Branch:** master (work committed directly, per prior consent)

## Goal

Add Arabic (`ar`) as a selectable UI language across the EKONT SMART REPORT web
app, with right-to-left (RTL) layout support, and localize the generated
Excel/PDF reports into Arabic. The existing four languages (en/tr/ru/de) and
their selection/persistence flow stay unchanged.

## Current State

- **Frontend i18n** (react-i18next): `src/i18n/index.ts` defines
  `SUPPORTED_LANGS = ['en','tr','ru','de']`, type `Lang`, eleven namespaces
  (`common, login, settings, dashboard, tags, trend, reports,
  advancedReports, plc, metrics, users`). Each namespace has four locale
  files under `src/i18n/locales/<lang>/<ns>.json`.
- **Language selection:** `src/components/LanguageSelector.tsx` renders a
  `<select>` over `SUPPORTED_LANGS` with a hardcoded `LABELS` map; on change
  it calls `i18n.changeLanguage(lang)` and persists via `updateMe(lang)`.
  Language also restored on login from `/auth/me` (AuthContext).
- **Persistence:** `i18n.on('languageChanged', ...)` writes `localStorage`;
  initial language read from `localStorage` with `en` fallback.
- **No RTL handling exists** anywhere — no `dir` attribute is ever set on
  `<html>`; all layout uses physical Tailwind utilities (`ml-/mr-`,
  `translate-x`, `left-0`, `border-r`, etc.).
- **Parity enforcement:** `src/i18n/parity.test.ts` checks key + placeholder
  parity, but only over `TARGET_LANGS = ['tr','ru','de']` and a hardcoded
  `NAMESPACES` map of en/tr/ru/de imports. New languages are NOT auto-covered.
- **Frontend hardcoded-string guard:** `scripts/check-hardcoded-strings.mjs`
  (run via `pnpm lint` / `lint:i18n`) scans source for untranslated JSX
  strings. Locale JSON files do not trigger it.
- **Backend report localization:** `app/i18n/report_labels.py` holds
  `LABELS: dict[str, dict[str,str]]` keyed by language (en/tr/ru/de, 39 keys
  each); `app/i18n/__init__.py::get_labels(lang)` returns the set with `en`
  fallback. Used by excel/pdf builders and the legacy inline export.
- **Backend language validation:** `app/api/auth.py` `UserUpdate.language` is
  `Literal["en","tr","ru","de"] | None`. `User.language` column is
  `String(5)` (fits `ar`). This is the ONLY backend language literal.
- **Backend label parity test:** `tests/test_report_labels.py`
  `test_all_languages_have_same_keys` iterates `("tr","ru","de")`.

## Decisions (from brainstorming)

1. **Full RTL**, scoped to the Layout shell + main structural directional
   fixes — NOT a pixel-perfect mirror of every page. Set `dir="rtl"` on
   `<html>` for Arabic so the browser flips text flow, table/form direction,
   and inline content automatically; then fix the structural utilities that
   do not auto-flip (sidebar side, mobile drawer slide direction, fixed
   left/right positioning, the few directional margins/borders in the shell).
2. **Reports localized into Arabic** — add an `ar` label set to
   `report_labels.py` so Arabic users' Excel/PDF reports carry Arabic
   headings.
3. **Translations are AI-generated drafts** (same posture as the existing
   ru/de sets) — flag for native-speaker review before production. Not a
   blocker for this work.

## Architecture & Components

### A. Frontend i18n registration

- Add `'ar'` to `SUPPORTED_LANGS` in `src/i18n/index.ts` (this also widens
  the `Lang` union automatically).
- Create eleven Arabic locale files: `src/i18n/locales/ar/<ns>.json` for each
  namespace, each with a key set **identical** to the corresponding
  `locales/en/<ns>.json` (Arabic values).
- Register the `ar` resources in `index.ts`: import each `ar*` JSON, add `ar:
  { ...all eleven namespaces }` to the `resources` object. (The `ns` array
  does not change — namespaces are language-independent.)
- `LanguageSelector.tsx`: extend `LABELS` with `ar: 'العربية'`.

### B. RTL direction handling

- Add a direction helper: `RTL_LANGS = new Set(['ar'])` and a function
  `dirFor(lang: string): 'rtl' | 'ltr'` in `src/i18n/index.ts` (exported).
- Apply direction whenever language changes AND on initial load:
  - In `index.ts`, set `document.documentElement.lang = lng` and
    `document.documentElement.dir = dirFor(lng)` inside the existing
    `i18n.on('languageChanged', ...)` handler (alongside the localStorage
    write), and once at module init for `initialLng`.
  - Because login restores language via `i18n.changeLanguage` (AuthContext),
    the `languageChanged` handler covers the post-login case too — no
    AuthContext change required.
- **Layout structural RTL fixes** (`src/components/Layout.tsx`) — the only
  component requiring deliberate mirroring:
  - Sidebar: it is `border-r` and slides from the left (`left-0`,
    `-translate-x-full` when hidden, `md:static`). Under RTL the sidebar
    should sit on the right. Convert to logical/`rtl:`-aware utilities so
    the drawer slides from the correct edge and the border is on the inner
    edge (e.g. `border-e`, `rtl:translate-x-full`, position via `start-0`
    or `rtl:right-0`).
  - Mobile top-bar and backdrop: ensure the hamburger/drawer open direction
    matches.
  - Any remaining physical spacing in the shell that visibly breaks
    (e.g. icon gaps `gap-*` are direction-agnostic and need no change;
    `ml-/mr-` become `ms-/me-` only where present).
- **Other pages:** rely on `dir="rtl"` cascade + Tailwind's logical behavior;
  do not individually mirror Dashboard/Tags/Trend/Reports/etc. Acceptable
  per the scope decision. (If a page has a glaringly broken control it may be
  fixed opportunistically, but full per-page mirroring is out of scope.)

### C. Backend

- `app/api/auth.py`: widen `UserUpdate.language` to
  `Literal["en","tr","ru","de","ar"] | None`.
- `app/i18n/report_labels.py`: add an `"ar"` entry to `LABELS` with all 39
  keys translated to Arabic; update the module docstring's language list.
  `get_labels` needs no change (fallback already generic).

### D. Tests

- `src/i18n/parity.test.ts`: add `ar` imports for all eleven namespaces, add
  `ar` to each `NAMESPACES` entry, and add `'ar'` to `TARGET_LANGS` so the
  Arabic files are key- and placeholder-parity-checked against `en`.
- `tests/test_report_labels.py`: add `'ar'` to the loop in
  `test_all_languages_have_same_keys`; add a `test_arabic_labels` asserting a
  couple of known Arabic values (mirrors `test_turkish_labels`).
- Backend: a test that `UserUpdate(language="ar")` validates (and a
  `PATCH /auth/me` with `{"language":"ar"}` persists it) — extends the
  existing auth/me tests.
- Frontend: extend/author a `LanguageSelector` test asserting the `ar` option
  renders (`العربية`); a focused test asserting `dirFor('ar') === 'rtl'` and
  that selecting Arabic sets `document.documentElement.dir = 'rtl'` (and back
  to `ltr` for a non-RTL language).

## Out of Scope (YAGNI)

- Pixel-perfect RTL mirroring of every page/component (only the Layout shell
  + structural fixes are in scope).
- Arabic-Indic numeral shaping or Hijri calendar (existing locale-aware
  number/date formatting is retained as-is).
- Native-speaker translation review (recommended follow-up, tracked
  separately).
- Adding Arabic to the agent-harness CLI or any non-web surface.

## Risks / Notes

- AI-generated Arabic strings may need wording fixes; the parity tests
  guarantee structural completeness, not linguistic quality.
- RTL is opt-in by language; en/tr/ru/de remain `ltr` and visually
  unchanged. The only shared-code change affecting all languages is the
  `dir`/`lang` attribute write, which sets `ltr` for them (current implicit
  default) — no visual change expected.
- The `String(5)` `User.language` column already accommodates `ar`; no DB
  migration is required.
