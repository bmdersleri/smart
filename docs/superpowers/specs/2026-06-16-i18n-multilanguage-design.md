# i18n Multi-Language Support — Design Spec

**Date:** 2026-06-16
**Status:** Approved, ready for implementation plan
**Scope:** Frontend UI + generated reports (Excel/PDF). API error/validation messages out of scope.

## Goal

Add internationalization (i18n) to the EKONT SMART REPORT so the React UI and the
generated Excel/PDF reports render in the user's chosen language. Ship four
languages in v1: Turkish (tr), English (en), Russian (ru), German (de).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Frontend UI + reports | Reports go to plant operators; they need them in their language. API errors stay English. |
| FE library | `react-i18next` | Mature, largest ecosystem, hook-based, plural/interpolation, lazy JSON. Clean with Vite + React 19. |
| Report locale source | `User.language` DB column | Server-side source of truth; report endpoints read `current_user.language`, no query param needed. |
| Languages | tr, en, ru, de | Plant is Turkish-operated; international norm wants EN; RU/DE requested. |
| Fallback language | `en` | International default; missing keys in any language fall back to English. |
| Language selector | Settings page **and** Layout header (globe dropdown) | Settings for the canonical control; header for quick access. |

## Architecture

### 1. Data model + language flow

- **`User.language`**: new column, `varchar(5)`, NOT NULL, default `'en'`, allowed
  values `en | tr | ru | de`. Added via Alembic migration. This is the **source of truth**.
- Login response and `GET /auth/me` include `language`.
- On auth load, the frontend calls `i18next.changeLanguage(user.language)` and mirrors
  the value to `localStorage` as a fast-boot hint (avoids a language flash before
  `/auth/me` resolves).
- The Settings (and header) language selector calls `changeLanguage()` locally and
  `PATCH /auth/me { language }` to persist.
- Report endpoints read `current_user.language` server-side and pass it to the report
  builders. No `?lang` query param.

### 2. Frontend structure

```
frontend/src/i18n/
  index.ts                      # i18next init: resources, fallbackLng='en', supportedLngs
  locales/
    en/ common.json dashboard.json tags.json trend.json reports.json
        advancedReports.json plc.json settings.json login.json metrics.json
    tr/ (same file set)
    ru/ (same file set)
    de/ (same file set)
```

- **Namespaces** are per-page plus a shared `common` (buttons, units, status labels,
  nav items, table chrome). Usage: `const { t } = useTranslation('tags'); t('title')`.
- `import './i18n'` runs in `main.tsx` before `<App />` mounts.
- **Language selector component** (`LanguageSelector.tsx`): a globe-icon dropdown listing
  the four languages. Rendered in the Settings page and the Layout header. On change it
  calls `i18next.changeLanguage(code)` and `PATCH /auth/me`.
- `SettingsContext` is the existing home for theme + trend height; language lives in
  `i18next` + `localStorage`, not duplicated into `SettingsContext`, to keep a single
  source of truth on the client.

### 3. Backend structure

```
backend/app/i18n/
  __init__.py        # get_labels(lang: str) -> dict  (falls back to 'en' for unknown lang)
  report_labels.py   # LABELS = {'en': {...}, 'tr': {...}, 'ru': {...}, 'de': {...}}
```

- `excel_builder` and `pdf_builder` gain a `lang` parameter. The report endpoints pass
  `current_user.language`; the builders resolve strings through `get_labels(lang)`.
- **Report label keys:** report titles, column headers, aggregation names
  (sum/avg/min/max/last/delta), date and period labels, footer/generated-at text.
- DB-sourced content (tag names, PLC names) is **not** translated — only static report chrome.

### 4. Extraction strategy (the ~277 hardcoded strings)

- The UI currently holds ~277 Turkish strings across 17 `.tsx` files
  (heaviest: AdvancedReports 69, Tags 56, Trend 34).
- Current Turkish text becomes the `tr/*.json` values verbatim. `en` is authored as the
  base translation. `ru` and `de` are AI-generated from EN and **flagged for human review**.
- Extraction proceeds page by page; each static string maps to a key in that page's namespace.
- **Not translated:** data returned from TanStack Query (tag names, PLC names, values) —
  only static UI chrome.

### 5. Testing

- **Frontend (vitest):**
  - i18n init loads all namespaces.
  - `changeLanguage` switches rendered text.
  - A missing key falls back to English (not a raw `namespace:key` string).
  - Smoke render of key pages in each language asserts no raw key leaks.
- **Backend (pytest):**
  - `get_labels(lang)` returns the correct dict per language.
  - Unknown language returns the English dict.
  - Report builders emit localized titles/headers for a given `lang`.
- **Regression guard (optional):** a lint script that flags newly introduced Turkish
  characters in `*.tsx` to prevent re-hardcoding.

## Build order

1. `User.language` column + Alembic migration; expose `language` in `/auth/me`; add `PATCH /auth/me`.
2. Frontend `i18next` scaffold + `common` namespace + `LanguageSelector` (Settings + header).
3. Extract page namespaces (batch the 17 files): dashboard, tags, trend, reports,
   advancedReports, plc, login, metrics, settings.
4. Backend `report_labels` + wire `excel_builder` / `pdf_builder` to `lang`.
5. RU/DE translation pass + human review.
6. Tests (FE vitest + BE pytest) + optional regression guard.

## Out of scope (v1)

- API error and validation message translation (server stays English).
- RTL languages (all four v1 languages are LTR).
- Translating DB-stored tag/PLC names or historical data.
- Number/date locale formatting beyond what `date-fns` already provides (revisit if needed).
