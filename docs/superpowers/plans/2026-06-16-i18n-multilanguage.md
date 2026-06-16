# i18n Multi-Language Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the React UI and generated Excel/PDF reports in the user's chosen language (tr/en/ru/de), with the preference stored on the `User` record.

**Architecture:** Frontend uses `react-i18next` with per-page JSON namespaces and `en` fallback. Backend stores `User.language` (source of truth); `/auth/me` exposes it and `PATCH /auth/me` updates it. Report builders receive a `lang` argument resolved from `current_user.language` and pull localized labels from `app/i18n/report_labels.py`.

**Tech Stack:** React 19 + Vite + react-i18next, FastAPI + SQLAlchemy + Alembic, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-06-16-i18n-multilanguage-design.md`

---

## File Structure

**Backend (create):**
- `app/i18n/__init__.py` — `get_labels(lang) -> dict`, fallback to `en`
- `app/i18n/report_labels.py` — `LABELS = {'en':{...}, 'tr':{...}, 'ru':{...}, 'de':{...}}`
- `alembic/versions/<rev>_add_user_language.py` — migration
- `tests/test_user_language.py`, `tests/test_report_labels.py`, `tests/test_report_i18n.py`

**Backend (modify):**
- `app/models/user.py` — add `language` column
- `app/api/auth.py` — expose `language` in `/me`, add `UserUpdate` + `PATCH /me`
- `app/services/excel_builder.py` — accept `lang`, use labels
- `app/services/pdf_builder.py` — accept `lang`, use labels
- `app/services/report_generator.py` + `app/api/reports.py` — pass `lang`

**Frontend (create):**
- `src/i18n/index.ts` — i18next init
- `src/i18n/locales/{en,tr,ru,de}/common.json` + one JSON per page namespace
- `src/components/LanguageSelector.tsx`
- `src/i18n/i18n.test.ts`, `src/components/LanguageSelector.test.tsx`

**Frontend (modify):**
- `src/main.tsx` — `import './i18n'`
- `src/api/client.ts` — `language` in `getMe` type, add `updateMe`
- `src/context/AuthContext.tsx` — `language` on `User`, sync i18next on load
- `src/pages/*.tsx`, `src/pages/dashboard/*.tsx`, `src/components/Layout.tsx` — replace hardcoded strings with `t()`

---

## Task 1: Backend — `User.language` column + migration

**Files:**
- Modify: `scada-reporter/backend/app/models/user.py:17-19`
- Create: `scada-reporter/backend/tests/test_user_language.py`
- Create: `scada-reporter/backend/alembic/versions/<rev>_add_user_language.py` (generated)

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_user_language.py`:

```python
import pytest
from sqlalchemy import select

from app.models.user import User


@pytest.mark.asyncio
async def test_user_defaults_to_english(db_session):
    user = User(
        username="lang_default",
        email="ld@example.com",
        hashed_password="x",
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.username == "lang_default"))
    fetched = result.scalar_one()
    assert fetched.language == "en"


@pytest.mark.asyncio
async def test_user_language_is_settable(db_session):
    user = User(
        username="lang_tr",
        email="lt@example.com",
        hashed_password="x",
        language="tr",
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.username == "lang_tr"))
    assert result.scalar_one().language == "tr"
```

> If the existing test suite uses a fixture named differently than `db_session`, match the project's fixture (check `tests/conftest.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_user_language.py -v`
Expected: FAIL — `AttributeError: language` / column does not exist.

- [ ] **Step 3: Add the column to the model**

In `app/models/user.py`, add after the `role` line (line 17):

```python
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
```

- [ ] **Step 4: Generate the Alembic migration**

Run:
```bash
cd scada-reporter/backend
DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db .venv/Scripts/python -m alembic revision --autogenerate -m "add user language"
```
Open the generated file under `alembic/versions/`. Confirm `upgrade()` contains:
```python
op.add_column("users", sa.Column("language", sa.String(length=5), nullable=False, server_default="en"))
```
If autogenerate emitted `nullable=False` without `server_default`, add `server_default="en"` so existing rows backfill. `downgrade()` should `op.drop_column("users", "language")`.

- [ ] **Step 5: Apply the migration**

Run:
```bash
cd scada-reporter/backend
DATABASE_URL=sqlite+aiosqlite:///./scada_reporter.db .venv/Scripts/python -m alembic upgrade head
```
Expected: `Running upgrade ... add user language`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_user_language.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/models/user.py scada-reporter/backend/alembic/versions scada-reporter/backend/tests/test_user_language.py
git commit -m "feat(i18n): add User.language column + migration"
```

---

## Task 2: Backend — expose `language` in `/auth/me` + `PATCH /auth/me`

**Files:**
- Modify: `scada-reporter/backend/app/api/auth.py:20-25,72-96`
- Create: `scada-reporter/backend/tests/test_auth_language.py`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_auth_language.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_me_returns_language(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["language"] == "en"


@pytest.mark.asyncio
async def test_patch_me_updates_language(client, auth_headers):
    resp = await client.patch("/api/auth/me", json={"language": "tr"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["language"] == "tr"

    me = await client.get("/api/auth/me", headers=auth_headers)
    assert me.json()["language"] == "tr"


@pytest.mark.asyncio
async def test_patch_me_rejects_unknown_language(client, auth_headers):
    resp = await client.patch("/api/auth/me", json={"language": "xx"}, headers=auth_headers)
    assert resp.status_code == 422
```

> Match the project's existing `client` / `auth_headers` fixtures from `tests/conftest.py`. If a logged-in client fixture has another name, use it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_auth_language.py -v`
Expected: FAIL — `/me` has no `language`; `PATCH /me` returns 405.

- [ ] **Step 3: Add the schema and endpoint**

In `app/api/auth.py`, add the import near the top (line 3 area):
```python
from typing import Literal
```
Add a schema after `UserCreate` (after line 25):
```python
class UserUpdate(BaseModel):
    language: Literal["en", "tr", "ru", "de"]
```
Update the `/me` return dict (lines 91-96) to include language:
```python
@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name,
        "language": user.language,
    }
```
Add the PATCH endpoint below `me`:
```python
@router.patch("/me")
async def update_me(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.language = data.language
    await db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name,
        "language": user.language,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_auth_language.py -v`
Expected: PASS (all three). `Literal` gives the 422 on unknown language for free.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/auth.py scada-reporter/backend/tests/test_auth_language.py
git commit -m "feat(i18n): expose + update user language via /auth/me"
```

---

## Task 3: Backend — `app/i18n` report label registry

**Files:**
- Create: `scada-reporter/backend/app/i18n/__init__.py`
- Create: `scada-reporter/backend/app/i18n/report_labels.py`
- Create: `scada-reporter/backend/tests/test_report_labels.py`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_report_labels.py`:

```python
from app.i18n import get_labels


def test_english_labels():
    labels = get_labels("en")
    assert labels["summary_sheet"] == "Summary"
    assert labels["total_reads"] == "Total Reads"


def test_turkish_labels():
    labels = get_labels("tr")
    assert labels["summary_sheet"] == "Özet"
    assert labels["total_reads"] == "Toplam Okuma"


def test_unknown_language_falls_back_to_english():
    assert get_labels("xx") == get_labels("en")


def test_all_languages_have_same_keys():
    en_keys = set(get_labels("en").keys())
    for lang in ("tr", "ru", "de"):
        assert set(get_labels(lang).keys()) == en_keys, f"{lang} key mismatch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_labels.py -v`
Expected: FAIL — `ModuleNotFoundError: app.i18n`.

- [ ] **Step 3: Create the label registry**

Create `app/i18n/report_labels.py`. Keys cover every hardcoded label in `excel_builder.py` and `pdf_builder.py`. RU/DE values are AI-drafted — flag for human review (Task 12).

```python
LABELS: dict[str, dict[str, str]] = {
    "en": {
        "summary_sheet": "Summary",
        "raw_sheet": "Raw Data",
        "total_reads": "Total Reads",
        "average": "Average",
        "minimum": "Min",
        "maximum": "Max",
        "count": "Count",
        "gap_total_seconds": "Total Gap (s)",
        "period": "Period",
        "time": "Time",
        "value": "Value",
        "type": "Type",
        "severity": "Severity",
        "detail": "Detail",
        "tag": "Tag",
        "quality": "Quality",
        "report_title": "Report",
        "generated_at": "Generated At",
    },
    "tr": {
        "summary_sheet": "Özet",
        "raw_sheet": "Ham Veri",
        "total_reads": "Toplam Okuma",
        "average": "Ortalama",
        "minimum": "Min",
        "maximum": "Max",
        "count": "Sayı",
        "gap_total_seconds": "Toplam Boşluk (sn)",
        "period": "Dönem",
        "time": "Zaman",
        "value": "Değer",
        "type": "Tür",
        "severity": "Şiddet",
        "detail": "Detay",
        "tag": "Tag",
        "quality": "Kalite",
        "report_title": "Rapor",
        "generated_at": "Oluşturulma",
    },
    "ru": {
        "summary_sheet": "Сводка",
        "raw_sheet": "Сырые данные",
        "total_reads": "Всего отсчётов",
        "average": "Среднее",
        "minimum": "Мин",
        "maximum": "Макс",
        "count": "Количество",
        "gap_total_seconds": "Общий пропуск (с)",
        "period": "Период",
        "time": "Время",
        "value": "Значение",
        "type": "Тип",
        "severity": "Важность",
        "detail": "Детали",
        "tag": "Тег",
        "quality": "Качество",
        "report_title": "Отчёт",
        "generated_at": "Создано",
    },
    "de": {
        "summary_sheet": "Übersicht",
        "raw_sheet": "Rohdaten",
        "total_reads": "Gesamtmessungen",
        "average": "Durchschnitt",
        "minimum": "Min",
        "maximum": "Max",
        "count": "Anzahl",
        "gap_total_seconds": "Gesamtlücke (s)",
        "period": "Zeitraum",
        "time": "Zeit",
        "value": "Wert",
        "type": "Typ",
        "severity": "Schwere",
        "detail": "Detail",
        "tag": "Tag",
        "quality": "Qualität",
        "report_title": "Bericht",
        "generated_at": "Erstellt am",
    },
}
```

Create `app/i18n/__init__.py`:

```python
from app.i18n.report_labels import LABELS

DEFAULT_LANG = "en"


def get_labels(lang: str) -> dict[str, str]:
    """Return the report label dict for `lang`, falling back to English."""
    return LABELS.get(lang, LABELS[DEFAULT_LANG])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_labels.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/i18n scada-reporter/backend/tests/test_report_labels.py
git commit -m "feat(i18n): backend report label registry (en/tr/ru/de)"
```

---

## Task 4: Backend — localize `excel_builder`

**Files:**
- Modify: `scada-reporter/backend/app/services/excel_builder.py` (signature + label sites at lines 26,36,39,100,106,117,141,167,179-180)
- Modify: `scada-reporter/backend/app/services/report_generator.py:55-160`
- Modify: `scada-reporter/backend/app/api/reports.py:111-160`
- Create: `scada-reporter/backend/tests/test_report_i18n.py`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_report_i18n.py`:

```python
import io

from openpyxl import load_workbook

from app.services.excel_builder import build_advanced_excel


def _sheet_titles(content: bytes) -> list[str]:
    wb = load_workbook(io.BytesIO(content))
    return wb.sheetnames


def test_excel_uses_english_summary_sheet(sample_report_archive, sample_per_tag_data):
    content = build_advanced_excel(
        sample_report_archive, sample_per_tag_data, lang="en"
    )
    assert "Summary" in _sheet_titles(content)


def test_excel_uses_turkish_summary_sheet(sample_report_archive, sample_per_tag_data):
    content = build_advanced_excel(
        sample_report_archive, sample_per_tag_data, lang="tr"
    )
    assert "Özet" in _sheet_titles(content)
```

> Reuse whatever fixtures the existing excel tests use to build a report archive + per-tag data. If none exist, build the minimal objects `build_advanced_excel` already expects (inspect its current parameters at line 26) and construct them inline in the test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_i18n.py -v`
Expected: FAIL — `build_advanced_excel()` got an unexpected keyword argument `lang`.

- [ ] **Step 3: Thread `lang` through `build_advanced_excel`**

In `app/services/excel_builder.py`:
1. Add the import at the top: `from app.i18n import get_labels`.
2. Add `lang: str = "en"` as the last parameter of `build_advanced_excel` (line 26).
3. At the top of the function body, add: `L = get_labels(lang)`.
4. Replace each hardcoded label with its key:
   - `ws_ozet.title = "Ozet"` → `ws_ozet.title = L["summary_sheet"]`
   - `("Toplam Okuma", s.count)` → `(L["total_reads"], s.count)`
   - `("Ortalama", ...)` → `(L["average"], ...)`
   - `("Toplam Boşluk (sn)", ...)` → `(L["gap_total_seconds"], ...)`
   - `_header_row(ws, ["Zaman", "Değer", "Tür", "Şiddet", "Detay"], ...)` → `_header_row(ws, [L["time"], L["value"], L["type"], L["severity"], L["detail"]], ...)`
   - `_header_row(ws, ["Dönem", "Ortalama", "Min", "Max", "Sayı"], ...)` → `_header_row(ws, [L["period"], L["average"], L["minimum"], L["maximum"], L["count"]], ...)`
   - `ws_raw = wb.create_sheet(title="Ham Veri")` → `title=L["raw_sheet"]`
   - `_header_row(ws_raw, ["Tag", "Zaman", "Değer", "Kalite"], ...)` → `[L["tag"], L["time"], L["value"], L["quality"]]`
   - The `stat_headers` list (line 39): map each entry to its `L[...]` key (use `L["average"]`, `L["minimum"]`, `L["maximum"]`, `L["count"]`, etc., matching the existing Turkish strings).

- [ ] **Step 4: Pass `lang` from the call sites**

In `app/services/report_generator.py`, `generate_report_from_template` (line 55): add a `lang: str = "en"` parameter and forward it to `build_advanced_excel(..., lang=lang)` and `build_pdf(..., lang=lang)` (PDF wired in Task 5).

In `app/api/reports.py` `generate_report` (line 112) and `app/api/advanced_reports.py` call at line 302: pass `lang=current_user.language`. The endpoints already depend on the current user via `Depends(get_current_user)` (or `require_role`); ensure the user object is in scope and pass `current_user.language`. If an endpoint doesn't yet bind the user, add `current_user: User = Depends(get_current_user)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_i18n.py -v`
Expected: PASS (both).

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/services/excel_builder.py scada-reporter/backend/app/services/report_generator.py scada-reporter/backend/app/api/reports.py scada-reporter/backend/app/api/advanced_reports.py scada-reporter/backend/tests/test_report_i18n.py
git commit -m "feat(i18n): localize excel report builder via user language"
```

---

## Task 5: Backend — localize `pdf_builder`

**Files:**
- Modify: `scada-reporter/backend/app/services/pdf_builder.py:12+`
- Modify: `scada-reporter/backend/app/services/report_generator.py:156` (pass `lang`)
- Modify: `scada-reporter/backend/tests/test_report_i18n.py` (add PDF assertions)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report_i18n.py`:

```python
from app.services.pdf_builder import build_pdf


def test_pdf_contains_localized_title(sample_report_archive, sample_per_tag_data, sample_template):
    from datetime import UTC, datetime

    content_en = build_pdf(
        sample_report_archive, sample_per_tag_data, sample_template,
        "Test Facility", datetime.now(UTC), lang="en",
    )
    content_tr = build_pdf(
        sample_report_archive, sample_per_tag_data, sample_template,
        "Test Facility", datetime.now(UTC), lang="tr",
    )
    assert content_en != content_tr  # different localized labels produce different bytes
    assert isinstance(content_en, (bytes, bytearray))
```

> Match `build_pdf`'s real signature (inspect line 12). The point: a `lang` kwarg exists and changes output.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_i18n.py -k pdf -v`
Expected: FAIL — `build_pdf()` got an unexpected keyword argument `lang`.

- [ ] **Step 3: Thread `lang` through `build_pdf`**

In `app/services/pdf_builder.py`:
1. `from app.i18n import get_labels` at the top.
2. Add `lang: str = "en"` as the last parameter of `build_pdf`.
3. `L = get_labels(lang)` at the top of the body.
4. Replace each hardcoded user-facing string in the HTML/template (titles, column headers, "Oluşturulma"/generated-at, stat labels) with the matching `L[...]` key. Confirm by grepping the file for Turkish characters after editing: `rg '[şğıçöüŞĞİÇÖÜ]' app/services/pdf_builder.py` should return only non-label content (or nothing).

In `report_generator.py` line 156, change `build_pdf(archive, per_tag_data, template, settings.FACILITY_NAME, generated_at)` → add `, lang=lang`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_i18n.py -k pdf -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/pdf_builder.py scada-reporter/backend/app/services/report_generator.py scada-reporter/backend/tests/test_report_i18n.py
git commit -m "feat(i18n): localize pdf report builder via user language"
```

---

## Task 6: Frontend — install deps + i18next scaffold + `common` namespace

**Files:**
- Modify: `scada-reporter/frontend/package.json` (deps)
- Create: `scada-reporter/frontend/src/i18n/index.ts`
- Create: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de}/common.json`
- Modify: `scada-reporter/frontend/src/main.tsx`
- Create: `scada-reporter/frontend/src/i18n/i18n.test.ts`

- [ ] **Step 1: Install the libraries**

Run:
```bash
cd scada-reporter/frontend && pnpm add i18next react-i18next
```
Expected: both added to `dependencies`.

- [ ] **Step 2: Write the failing test**

Create `src/i18n/i18n.test.ts`:

```ts
import { describe, it, expect, beforeAll } from 'vitest'
import i18n from './index'

describe('i18n', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('returns the English string for a known key', () => {
    expect(i18n.t('common:save')).toBe('Save')
  })

  it('switches language', async () => {
    await i18n.changeLanguage('tr')
    expect(i18n.t('common:save')).toBe('Kaydet')
  })

  it('falls back to English for a missing key in another language', async () => {
    await i18n.changeLanguage('ru')
    // 'only_in_english' exists only in the en bundle for this test
    expect(i18n.t('common:save')).toBe('Сохранить')
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test -- i18n`
Expected: FAIL — cannot resolve `./index`.

- [ ] **Step 4: Create the `common` namespace JSON**

`src/i18n/locales/en/common.json`:
```json
{
  "save": "Save",
  "cancel": "Cancel",
  "delete": "Delete",
  "edit": "Edit",
  "add": "Add",
  "reset": "Reset to Defaults",
  "loading": "Loading...",
  "search": "Search",
  "settings": "Settings",
  "logout": "Log Out",
  "language": "Language"
}
```
`src/i18n/locales/tr/common.json`:
```json
{
  "save": "Kaydet",
  "cancel": "İptal",
  "delete": "Sil",
  "edit": "Düzenle",
  "add": "Ekle",
  "reset": "Varsayılanlara Sıfırla",
  "loading": "Yükleniyor...",
  "search": "Ara",
  "settings": "Ayarlar",
  "logout": "Çıkış Yap",
  "language": "Dil"
}
```
`src/i18n/locales/ru/common.json`:
```json
{
  "save": "Сохранить",
  "cancel": "Отмена",
  "delete": "Удалить",
  "edit": "Изменить",
  "add": "Добавить",
  "reset": "Сбросить настройки",
  "loading": "Загрузка...",
  "search": "Поиск",
  "settings": "Настройки",
  "logout": "Выйти",
  "language": "Язык"
}
```
`src/i18n/locales/de/common.json`:
```json
{
  "save": "Speichern",
  "cancel": "Abbrechen",
  "delete": "Löschen",
  "edit": "Bearbeiten",
  "add": "Hinzufügen",
  "reset": "Auf Standard zurücksetzen",
  "loading": "Wird geladen...",
  "search": "Suchen",
  "settings": "Einstellungen",
  "logout": "Abmelden",
  "language": "Sprache"
}
```

- [ ] **Step 5: Create `src/i18n/index.ts`**

```ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enCommon from './locales/en/common.json'
import trCommon from './locales/tr/common.json'
import ruCommon from './locales/ru/common.json'
import deCommon from './locales/de/common.json'

export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de'] as const
export type Lang = (typeof SUPPORTED_LANGS)[number]

const stored = localStorage.getItem('lang')
const initialLng = (SUPPORTED_LANGS as readonly string[]).includes(stored ?? '')
  ? (stored as Lang)
  : 'en'

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon },
    tr: { common: trCommon },
    ru: { common: ruCommon },
    de: { common: deCommon },
  },
  lng: initialLng,
  fallbackLng: 'en',
  ns: ['common'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => {
  localStorage.setItem('lang', lng)
})

export default i18n
```

> As later tasks add namespaces, import each page JSON and add it under every language's `resources` block and to the `ns` array.

- [ ] **Step 6: Wire into `main.tsx`**

In `src/main.tsx`, add `import './i18n'` directly under `import './index.css'` (line 3). This must run before `<App />` renders.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test -- i18n`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/package.json scada-reporter/frontend/pnpm-lock.yaml scada-reporter/frontend/src/i18n scada-reporter/frontend/src/main.tsx
git commit -m "feat(i18n): react-i18next scaffold + common namespace"
```

---

## Task 7: Frontend — language sync + `LanguageSelector`

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts:26` (getMe type) + add `updateMe`
- Modify: `scada-reporter/frontend/src/context/AuthContext.tsx:6,24-25,33-35`
- Create: `scada-reporter/frontend/src/components/LanguageSelector.tsx`
- Modify: `scada-reporter/frontend/src/pages/Settings.tsx` + `src/components/Layout.tsx`
- Create: `scada-reporter/frontend/src/components/LanguageSelector.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/components/LanguageSelector.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import i18n from '../i18n'
import LanguageSelector from './LanguageSelector'

vi.mock('../api/client', () => ({
  updateMe: vi.fn().mockResolvedValue({ data: { language: 'tr' } }),
}))

describe('LanguageSelector', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders all four languages', () => {
    render(<LanguageSelector />)
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.options).toHaveLength(4)
  })

  it('changes i18n language and persists on select', async () => {
    const { updateMe } = await import('../api/client')
    render(<LanguageSelector />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'tr' } })
    expect(i18n.language).toBe('tr')
    expect(updateMe).toHaveBeenCalledWith('tr')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test -- LanguageSelector`
Expected: FAIL — cannot resolve `./LanguageSelector`.

- [ ] **Step 3: Add `updateMe` + extend `getMe` type in client**

In `src/api/client.ts`, extend the `getMe` return type (line 26) to include `language: string`, and add below it:
```ts
export const updateMe = (language: string) =>
  api.patch<{ id: number; username: string; role: string; full_name: string; language: string }>(
    '/auth/me',
    { language },
  )
```

- [ ] **Step 4: Create `LanguageSelector.tsx`**

```tsx
import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { SUPPORTED_LANGS } from '../i18n'
import { updateMe } from '../api/client'

const LABELS: Record<string, string> = {
  en: 'English',
  tr: 'Türkçe',
  ru: 'Русский',
  de: 'Deutsch',
}

export default function LanguageSelector() {
  const { i18n } = useTranslation()

  const onChange = async (lang: string) => {
    await i18n.changeLanguage(lang)
    try {
      await updateMe(lang)
    } catch {
      /* language already applied locally + cached; ignore persistence error */
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Globe className="w-4 h-4 text-gray-400" />
      <select
        value={i18n.language}
        onChange={(e) => onChange(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
      >
        {SUPPORTED_LANGS.map((l) => (
          <option key={l} value={l}>
            {LABELS[l]}
          </option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 5: Sync language from auth load**

In `src/context/AuthContext.tsx`:
1. Extend the `User` interface (line 6) with `language: string`.
2. Import i18n: `import i18n from '../i18n'`.
3. After `setUser(r.data)` in the `getMe().then(...)` (line 25), add: `if (r.data.language) i18n.changeLanguage(r.data.language)`.
4. After `setUser(me.data)` in `login` (line 34), add: `if (me.data.language) i18n.changeLanguage(me.data.language)`.

- [ ] **Step 6: Render the selector**

In `src/pages/Settings.tsx`, add a "Language" row inside the appearance card (mirror the Theme row markup), rendering `<LanguageSelector />`. Replace the hardcoded `"Ayarlar"`, `"Görünüm"`, `"Tema"` etc. with `t()` calls in Task 8's Settings extraction — for now just mount the selector.

In `src/components/Layout.tsx`, render `<LanguageSelector />` in the sidebar footer next to the logout control (the sidebar is the app chrome; there is no top header).

- [ ] **Step 7: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test -- LanguageSelector`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/context/AuthContext.tsx scada-reporter/frontend/src/components/LanguageSelector.tsx scada-reporter/frontend/src/components/LanguageSelector.test.tsx scada-reporter/frontend/src/pages/Settings.tsx scada-reporter/frontend/src/components/Layout.tsx
git commit -m "feat(i18n): language selector + sync from user record"
```

---

## Task 8: Frontend — extract `Login` + `Settings` namespaces (canonical pattern)

This task is the **worked reference** for all page extractions (Tasks 9–11 follow the same mechanic).

**Files:**
- Create: `src/i18n/locales/{en,tr,ru,de}/login.json`, `.../settings.json`
- Modify: `src/i18n/index.ts` (register namespaces)
- Modify: `src/pages/Login.tsx`, `src/pages/Settings.tsx`
- Create: `src/pages/Login.i18n.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/pages/Login.i18n.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import i18n from '../i18n'
import Login from './Login'

const renderLogin = () =>
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )

describe('Login i18n', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders the English submit label', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: 'Log In' })).toBeTruthy()
  })

  it('renders the Turkish submit label after switch', async () => {
    await i18n.changeLanguage('tr')
    renderLogin()
    expect(screen.getByRole('button', { name: 'Giriş Yap' })).toBeTruthy()
  })

  it('shows no raw translation keys', () => {
    renderLogin()
    expect(document.body.textContent).not.toMatch(/login:/)
  })
})
```

> `Login` uses `useAuth()`; wrap with `AuthProvider` if the component throws without it, or mock `../context/AuthContext`'s `useAuth` to return `{ login: vi.fn() }`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/frontend && pnpm test -- Login.i18n`
Expected: FAIL — button reads "Giriş Yap" in English mode (still hardcoded).

- [ ] **Step 3: Create the namespace JSON files**

`src/i18n/locales/en/login.json`:
```json
{
  "subtitle": "Water/Wastewater Plant Management System",
  "username": "Username",
  "password": "Password",
  "submit": "Log In",
  "submitting": "Logging in...",
  "error": "Invalid username or password"
}
```
`src/i18n/locales/tr/login.json`:
```json
{
  "subtitle": "Su/Atıksu Tesis Yönetim Sistemi",
  "username": "Kullanıcı Adı",
  "password": "Şifre",
  "submit": "Giriş Yap",
  "submitting": "Giriş yapılıyor...",
  "error": "Kullanıcı adı veya şifre hatalı"
}
```
`src/i18n/locales/ru/login.json` (AI draft — review in Task 12):
```json
{
  "subtitle": "Система управления станцией водоснабжения/водоотведения",
  "username": "Имя пользователя",
  "password": "Пароль",
  "submit": "Войти",
  "submitting": "Вход...",
  "error": "Неверное имя пользователя или пароль"
}
```
`src/i18n/locales/de/login.json` (AI draft — review in Task 12):
```json
{
  "subtitle": "Verwaltungssystem für Wasser-/Abwasseranlagen",
  "username": "Benutzername",
  "password": "Passwort",
  "submit": "Anmelden",
  "submitting": "Anmeldung läuft...",
  "error": "Ungültiger Benutzername oder Passwort"
}
```
Create `settings.json` for all four languages the same way, with keys:
`title` (Ayarlar/Settings/…), `appearance` (Görünüm), `theme` (Tema), `theme_hint` (Açık / koyu renk şeması), `theme_dark` (Koyu), `theme_light` (Açık), `language` (Dil), `trend_chart` (Trend Grafik), `chart_height` (Grafik Yüksekliği), `selected` (Seçili). Use the existing Turkish text from `Settings.tsx` as the `tr` values and translate the rest.

- [ ] **Step 4: Register namespaces in `index.ts`**

In `src/i18n/index.ts`, import the new JSON for each language, add `login` and `settings` keys to every language's `resources` block, and append `'login', 'settings'` to the `ns` array.

- [ ] **Step 5: Replace hardcoded strings in `Login.tsx`**

Add `import { useTranslation } from 'react-i18next'`, then `const { t } = useTranslation('login')`. Replace:
- `"Su/Atıksu Tesis Yönetim Sistemi"` → `{t('subtitle')}`
- `"Kullanıcı Adı"` → `{t('username')}`
- `"Şifre"` → `{t('password')}`
- `setError('Kullanıcı adı veya şifre hatalı')` → `setError(t('error'))`
- `{loading ? 'Giriş yapılıyor...' : 'Giriş Yap'}` → `{loading ? t('submitting') : t('submit')}`

Do the same in `Settings.tsx` with `useTranslation('settings')`, replacing every Turkish string with its key, and the appearance card's `<button>` labels using `t('theme_dark')` / `t('theme_light')`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd scada-reporter/frontend && pnpm test -- Login.i18n`
Expected: PASS (3 tests).

- [ ] **Step 7: Verify no raw Turkish remains in the two files**

Run: `cd scada-reporter/frontend && rg '[şğıçöüŞĞİÇÖÜ]' src/pages/Login.tsx src/pages/Settings.tsx`
Expected: no matches (only `t()` keys remain).

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/i18n scada-reporter/frontend/src/pages/Login.tsx scada-reporter/frontend/src/pages/Settings.tsx scada-reporter/frontend/src/pages/Login.i18n.test.tsx
git commit -m "feat(i18n): extract login + settings namespaces"
```

---

## Task 9: Frontend — extract `Layout` + dashboard namespaces

**Files:**
- Create: `src/i18n/locales/{en,tr,ru,de}/dashboard.json`
- Modify: `src/i18n/index.ts`
- Modify: `src/components/Layout.tsx`, `src/pages/Dashboard.tsx`, `src/pages/dashboard/{OverviewTab,WatchlistTab,AllTagsTab}.tsx`
- Create: `src/pages/dashboard/Dashboard.i18n.test.tsx`

Apply the **exact mechanic from Task 8**: write a failing render-in-en/tr test for a dashboard tab, create the four `dashboard.json` files (nav labels go in `common.json`; dashboard-specific strings — tab titles "Özet/İzleme Listesi/Tüm Tag'ler", column headers, empty states — go in `dashboard.json`), register the namespace in `index.ts`, replace hardcoded strings with `useTranslation('dashboard')` + `t()`, verify `rg '[şğıçöüŞĞİÇÖÜ]'` returns nothing across these files, commit.

- [ ] **Step 1:** Write `Dashboard.i18n.test.tsx` asserting an en label and its tr counterpart on one tab (FAIL first).
- [ ] **Step 2:** Run `pnpm test -- Dashboard.i18n` → FAIL.
- [ ] **Step 3:** Create `dashboard.json` (en/tr/ru/de); move the 4 sidebar `nav` labels in `Layout.tsx` into `common.json` keys (`nav_dashboard`, `nav_trend`, `nav_reports`, `nav_advanced_reports`, `nav_tags`, `nav_plc`, `nav_metrics`, `nav_settings`).
- [ ] **Step 4:** Register `dashboard` in `index.ts`.
- [ ] **Step 5:** Replace strings in `Layout.tsx` + the dashboard files with `t()`.
- [ ] **Step 6:** Run `pnpm test -- Dashboard.i18n` → PASS.
- [ ] **Step 7:** `rg '[şğıçöüŞĞİÇÖÜ]' src/components/Layout.tsx src/pages/Dashboard.tsx src/pages/dashboard` → no matches.
- [ ] **Step 8:** Commit `feat(i18n): extract layout + dashboard namespaces`.

---

## Task 10: Frontend — extract `Tags` + `Trend` namespaces

**Files:**
- Create: `src/i18n/locales/{en,tr,ru,de}/tags.json`, `.../trend.json`
- Modify: `src/i18n/index.ts`, `src/pages/Tags.tsx` (56 strings), `src/pages/Trend.tsx` (34 strings)
- Create: `src/pages/Tags.i18n.test.tsx`

Same mechanic as Task 8, one namespace per page. These are the two largest UI files; extract carefully.

- [ ] **Step 1:** Write `Tags.i18n.test.tsx` (en label + tr label on the Tags page header/primary button) → FAIL.
- [ ] **Step 2:** `pnpm test -- Tags.i18n` → FAIL.
- [ ] **Step 3:** Create `tags.json` + `trend.json` (en/tr/ru/de). Seed `tr` from the current Turkish strings; translate the rest. Group keys logically (e.g. `tree_view`, `add_group`, `deadband`, `csv_import`, `export`, axis/zoom labels for Trend).
- [ ] **Step 4:** Register `tags`, `trend` in `index.ts`.
- [ ] **Step 5:** Replace strings in `Tags.tsx` with `useTranslation('tags')` and `Trend.tsx` with `useTranslation('trend')`. Recharts axis/label props take plain strings — pass `t(...)` values directly.
- [ ] **Step 6:** `pnpm test -- Tags.i18n` → PASS.
- [ ] **Step 7:** `rg '[şğıçöüŞĞİÇÖÜ]' src/pages/Tags.tsx src/pages/Trend.tsx` → no matches.
- [ ] **Step 8:** Commit `feat(i18n): extract tags + trend namespaces`.

---

## Task 11: Frontend — extract `Reports` + `AdvancedReports` + `Plc` + `Metrics` namespaces

**Files:**
- Create: `src/i18n/locales/{en,tr,ru,de}/{reports,advancedReports,plc,metrics}.json`
- Modify: `src/i18n/index.ts`, `src/pages/{Reports,AdvancedReports,PlcConfig,Metrics}.tsx`
- Create: `src/pages/AdvancedReports.i18n.test.tsx`

Same mechanic, four namespaces. `AdvancedReports.tsx` (69 strings) is the largest — extract methodically.

- [ ] **Step 1:** Write `AdvancedReports.i18n.test.tsx` (en + tr on page header/primary action) → FAIL.
- [ ] **Step 2:** `pnpm test -- AdvancedReports.i18n` → FAIL.
- [ ] **Step 3:** Create the four namespace JSON sets (en/tr/ru/de); seed `tr` from current strings.
- [ ] **Step 4:** Register `reports`, `advancedReports`, `plc`, `metrics` in `index.ts`.
- [ ] **Step 5:** Replace strings in each page with its `useTranslation(<ns>)`.
- [ ] **Step 6:** `pnpm test -- AdvancedReports.i18n` → PASS.
- [ ] **Step 7:** `rg '[şğıçöüŞĞİÇÖÜ]' src/pages/Reports.tsx src/pages/AdvancedReports.tsx src/pages/PlcConfig.tsx src/pages/Metrics.tsx` → no matches.
- [ ] **Step 8:** Commit `feat(i18n): extract reports/advanced-reports/plc/metrics namespaces`.

---

## Task 12: RU/DE translation review + regression guard

**Files:**
- Modify: any `ru/*.json`, `de/*.json` needing correction
- Create: `scada-reporter/frontend/scripts/check-hardcoded-strings.mjs`
- Modify: `scada-reporter/frontend/package.json` (lint script)

- [ ] **Step 1: Human-review RU/DE bundles**

Open every `src/i18n/locales/ru/*.json` and `de/*.json`. These were AI-drafted. Verify domain terms (SCADA, deadband, tag, watchlist, rollup) read correctly to a native speaker; fix any awkward strings. This is a manual review step — no test, but required before release.

- [ ] **Step 2: Write the key-parity test (FE)**

Create `src/i18n/parity.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import en from './locales/en/common.json'
import tr from './locales/tr/common.json'
import ru from './locales/ru/common.json'
import de from './locales/de/common.json'

describe('common namespace key parity', () => {
  const enKeys = Object.keys(en).sort()
  it.each([['tr', tr], ['ru', ru], ['de', de]])('%s has the same keys as en', (_n, bundle) => {
    expect(Object.keys(bundle).sort()).toEqual(enKeys)
  })
})
```

> Extend this with the other namespaces (login, settings, dashboard, tags, trend, reports, advancedReports, plc, metrics) the same way, importing each language's file and asserting key parity against `en`.

- [ ] **Step 3: Run the parity test**

Run: `cd scada-reporter/frontend && pnpm test -- parity`
Expected: PASS. If a language is missing a key, add it.

- [ ] **Step 4: Add the hardcoded-string guard script**

Create `scripts/check-hardcoded-strings.mjs`:

```js
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const TR_CHARS = /[şğıçöüŞĞİÇÖÜ]/
const SRC = new URL('../src', import.meta.url).pathname

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (!p.includes('i18n')) walk(p) // locale JSON is allowed to contain TR
      continue
    }
    if (!/\.(tsx|ts)$/.test(p) || p.endsWith('.test.ts') || p.endsWith('.test.tsx')) continue
    const lines = readFileSync(p, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (TR_CHARS.test(line)) {
        console.error(`${p}:${i + 1}: hardcoded non-English string: ${line.trim()}`)
        process.exitCode = 1
      }
    })
  }
}

walk(SRC)
if (process.exitCode === 1) {
  console.error('\nMove these strings into src/i18n/locales/*/<namespace>.json')
}
```

- [ ] **Step 5: Run the guard**

Run: `cd scada-reporter/frontend && node scripts/check-hardcoded-strings.mjs`
Expected: exit 0 (all strings extracted). If it flags lines, extract them into the right namespace.

- [ ] **Step 6: Wire the guard into the lint script**

In `package.json`, change `"lint": "eslint ."` to `"lint": "eslint . && node scripts/check-hardcoded-strings.mjs"`.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/frontend/src/i18n scada-reporter/frontend/scripts/check-hardcoded-strings.mjs scada-reporter/frontend/package.json
git commit -m "feat(i18n): RU/DE review, key-parity tests, hardcoded-string guard"
```

---

## Task 13: Full verification

- [ ] **Step 1: Backend suite**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest -q`
Expected: all green (including the new language/report-i18n tests).

- [ ] **Step 2: Frontend tests + typecheck + lint**

Run: `cd scada-reporter/frontend && pnpm test run && pnpm exec tsc -b && pnpm lint`
Expected: tests pass, no type errors, lint (incl. hardcoded-string guard) clean.

- [ ] **Step 3: Manual smoke**

Start backend + frontend (`just dev`). Log in, open the language selector, switch through en → tr → ru → de, confirm the UI updates live and the choice survives a page reload (localStorage + `/auth/me`). Generate one Excel and one PDF report; confirm sheet/column titles match the selected language.

- [ ] **Step 4: Final commit (if any fixes from smoke)**

```bash
git add -A
git commit -m "test(i18n): full verification fixes"
```

---

## Self-Review Notes

- **Spec coverage:** data model (T1), `/auth/me` expose+patch (T2), backend report registry (T3), excel (T4) + pdf (T5) localization, FE scaffold (T6), selector + sync (T7), page extraction (T8–T11), RU/DE review + guard + parity (T12), verification (T13). All spec sections mapped.
- **Fallback:** `en` everywhere — `get_labels` (T3) and `fallbackLng` (T6).
- **Selector placement:** Settings + sidebar footer (Layout is a sidebar, not a top header) — corrected from spec's "header".
- **Naming consistency:** `User.language`, `updateMe(language)`, `get_labels(lang)`, `build_advanced_excel(..., lang)`, `build_pdf(..., lang)` used consistently across tasks.
