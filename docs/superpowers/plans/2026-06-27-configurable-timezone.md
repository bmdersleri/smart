# Configurable Timezone for Lab Data Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a facility-global, admin-configurable IANA timezone (default `Europe/Istanbul`) and apply it to lab data entry so the recorded/displayed time matches the operator's wall clock instead of being ~3 hours behind (UTC).

**Architecture:** A backend key/value `AppSetting` store + `GET /api/settings` (read) / `PUT /api/settings/timezone` (admin) endpoints hold the timezone. The frontend reads it via a `useTimezone()` query hook and applies it in the lab entry/records components through pure `Intl`-based helpers in `src/utils/labTime.ts`. `sampled_at` stays UTC in storage.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy async / Alembic / `zoneinfo`; React 19 / TypeScript / TanStack Query / hand-written axios / `Intl.DateTimeFormat`.

## Global Constraints

- Python baseline **3.14**. Backend TDD per-file: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v` (from `scada-reporter/backend`; Python is `python`, venv `.venv/Scripts/python`).
- Lint/type gate `just check` before each task's final commit.
- Single Alembic head preserved. Current head **`a1b2c3d4e5f7`** → new migration `down_revision = "a1b2c3d4e5f7"`.
- New model imported in `app/main.py`'s `# noqa: F401` block.
- Endpoints: `GET /settings` behind `get_current_user`; `PUT /settings/timezone` behind `require_role("admin")` + `require_writable`. Router prefix `/settings`; mounted with `prefix="/api"`.
- Default timezone constant: `DEFAULT_TIMEZONE = "Europe/Istanbul"`. Validate submitted zones against `zoneinfo.available_timezones()` (422 on unknown).
- `sampled_at` is stored UTC; the configured timezone governs entry default + display only.
- Frontend: NO `prettier --write` (compact style); hand-written axios client (`api.get`/`api.put`, read `.data`); i18n strings localized (the affected pages use their existing namespaces — `lab` for lab components, the Settings page's namespace for the card). TanStack Query is the data layer.
- Branch `master`, commit directly (dev-phase). Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Commit discipline (drift-heavy repo):** `git checkout master` at start + before commit; commit with an EXPLICIT pathspec and put `-m "msg"` BEFORE the `--` separator: `git commit -m "<msg>" -- <file1> <file2>`. For a NEW untracked file, `git add <file>` first, then `git commit -m ... -- <file>`. NEVER `git add -A` / bare `git commit`.

---

## File Structure

- `app/models/app_setting.py` — `AppSetting` key/value model.
- `alembic/versions/<rev>_app_settings.py` — `app_settings` table.
- `app/api/app_settings.py` — `/settings` router (GET + PUT timezone).
- `app/main.py` — model import + router include.
- `tests/test_app_settings.py` — endpoint + model tests.
- `frontend/src/utils/labTime.ts` (+ `.test.ts`) — pure timezone helpers.
- `frontend/src/api/client.ts` — `getAppSettings`, `updateTimezone`.
- `frontend/src/hooks/useTimezone.ts` — query hook.
- `frontend/src/pages/lab/{SingleSampleTab,BatchTab,RecordsTab}.tsx` — apply tz.
- `frontend/src/pages/Settings.tsx` — admin Timezone card.
- `frontend/src/i18n/locales/*/lab.json` — timezone-card keys (the card lives in Settings but uses the `lab` namespace already mounted there, or add to the Settings page's namespace — match the page).

---

## Task 1: Backend AppSetting store + `/settings` endpoints

**Files:**
- Create: `scada-reporter/backend/app/models/app_setting.py`
- Create: `scada-reporter/backend/alembic/versions/b2c3d4e5f6a8_app_settings.py`
- Create: `scada-reporter/backend/app/api/app_settings.py`
- Modify: `scada-reporter/backend/app/main.py`
- Test: `scada-reporter/backend/tests/test_app_settings.py`

**Interfaces:**
- Produces: `AppSetting(key: str [pk], value: str)`; router with `GET /settings` → `{"timezone": str}` and `PUT /settings/timezone` (body `{"timezone": str}`) → `{"timezone": str}`; `DEFAULT_TIMEZONE = "Europe/Istanbul"`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_app_settings.py`:

```python
from types import SimpleNamespace

import pytest

from app.api.auth import get_current_user
from app.main import app


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_settings_default_when_unset(client):
    _as("operator")
    r = await client.get("/api/settings")
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "Europe/Istanbul"


@pytest.mark.asyncio
async def test_admin_sets_timezone_then_get_returns_it(client):
    _as("admin")
    put = await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    assert put.status_code == 200, put.text
    assert put.json()["timezone"] == "UTC"
    _as("operator")
    got = await client.get("/api/settings")
    assert got.json()["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_invalid_timezone_422(client):
    _as("admin")
    r = await client.put("/api/settings/timezone", json={"timezone": "Mars/Phobos"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_put_403(client):
    _as("operator")
    r = await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_set_timezone_is_upsert(client):
    _as("admin")
    await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    await client.put("/api/settings/timezone", json={"timezone": "Europe/Berlin"})
    _as("operator")
    got = await client.get("/api/settings")
    assert got.json()["timezone"] == "Europe/Berlin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_app_settings.py -p no:randomly -n0 -v`
Expected: FAIL — 404 (router/model missing).

- [ ] **Step 3: Create the model**

Create `scada-reporter/backend/app/models/app_setting.py`:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
```

Register it in `scada-reporter/backend/app/main.py`'s `# noqa: F401` import block (next to `from app.models import lab as _lab  # noqa: F401`):

```python
from app.models import app_setting as _app_setting  # noqa: F401
```

- [ ] **Step 4: Create the migration**

Create `scada-reporter/backend/alembic/versions/b2c3d4e5f6a8_app_settings.py`:

```python
"""app_settings key/value table

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-27 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
```

- [ ] **Step 5: Create the router**

Create `scada-reporter/backend/app/api/app_settings.py`:

```python
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_TIMEZONE = "Europe/Istanbul"


class TimezoneIn(BaseModel):
    timezone: str


async def _get_value(db: AsyncSession, key: str) -> str | None:
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row else None


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    tz = await _get_value(db, "timezone")
    return {"timezone": tz or DEFAULT_TIMEZONE}


@router.put("/timezone")
async def put_timezone(
    data: TimezoneIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
) -> dict:
    if data.timezone not in zoneinfo.available_timezones():
        raise HTTPException(status_code=422, detail="Geçersiz saat dilimi")
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == "timezone"))
    ).scalar_one_or_none()
    if row is not None:
        row.value = data.timezone
    else:
        db.add(AppSetting(key="timezone", value=data.timezone))
    await db.commit()
    return {"timezone": data.timezone}
```

In `scada-reporter/backend/app/main.py`, add the import alongside the other `from app.api import ...` lines and the include near the other `app.include_router(...)` lines:

```python
from app.api import app_settings  # noqa: E402  (top api import group)
app.include_router(app_settings.router, prefix="/api")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_app_settings.py -p no:randomly -n0 -v`
Expected: PASS (5 passed). Tables are auto-created from `Base.metadata` by the conftest fixture.

- [ ] **Step 7: Verify migration head + checks + commit**

Run: `just migrate` then `.venv/Scripts/python -m alembic heads` (single head `b2c3d4e5f6a8`). Then `just check`.

```bash
git checkout master
git add scada-reporter/backend/app/models/app_setting.py scada-reporter/backend/app/api/app_settings.py scada-reporter/backend/alembic/versions/b2c3d4e5f6a8_app_settings.py scada-reporter/backend/tests/test_app_settings.py
git commit -m "feat(settings): app_settings store + GET/PUT timezone endpoints" -- scada-reporter/backend/app/models/app_setting.py scada-reporter/backend/app/api/app_settings.py scada-reporter/backend/app/main.py scada-reporter/backend/alembic/versions/b2c3d4e5f6a8_app_settings.py scada-reporter/backend/tests/test_app_settings.py
```
(footer in the message; if pre-commit reformats, re-run the same commit. `main.py` is already tracked so it needs no `git add`.)

---

## Task 2: Frontend timezone helpers + client + hook

**Files:**
- Create: `scada-reporter/frontend/src/utils/labTime.ts`
- Test: `scada-reporter/frontend/src/utils/labTime.test.ts`
- Modify: `scada-reporter/frontend/src/api/client.ts`
- Create: `scada-reporter/frontend/src/hooks/useTimezone.ts`

**Interfaces:**
- Consumes: Task 1 endpoints.
- Produces: `nowInTz(tz)`, `wallclockToUtcIso(value, tz)`, `utcToTzInput(iso, tz)`, `utcToTzDisplay(iso, tz, locale?)`; `getAppSettings()`, `updateTimezone(tz)`; `useTimezone(): string`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/frontend/src/utils/labTime.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { nowInTz, utcToTzInput, wallclockToUtcIso } from './labTime'

describe('labTime', () => {
  it('wallclockToUtcIso treats the value as Istanbul wall-clock (+03)', () => {
    expect(wallclockToUtcIso('2026-06-27T12:00', 'Europe/Istanbul')).toBe(
      '2026-06-27T09:00:00.000Z',
    )
  })
  it('wallclockToUtcIso is identity-ish for UTC', () => {
    expect(wallclockToUtcIso('2026-06-27T09:00', 'UTC')).toBe('2026-06-27T09:00:00.000Z')
  })
  it('utcToTzInput renders a UTC instant in Istanbul local (+03)', () => {
    expect(utcToTzInput('2026-06-27T09:00:00.000Z', 'Europe/Istanbul')).toBe('2026-06-27T12:00')
  })
  it('round-trips wall-clock -> utc -> wall-clock', () => {
    const utc = wallclockToUtcIso('2026-06-27T08:30', 'Europe/Istanbul')
    expect(utcToTzInput(utc, 'Europe/Istanbul')).toBe('2026-06-27T08:30')
  })
  it('nowInTz returns a YYYY-MM-DDTHH:mm string', () => {
    expect(nowInTz('UTC')).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/utils/labTime.test.ts`
Expected: FAIL — cannot resolve `./labTime`.

- [ ] **Step 3: Implement the helpers**

Create `scada-reporter/frontend/src/utils/labTime.ts`:

```ts
// Timezone-aware helpers for lab data entry. The configured IANA timezone
// governs the entry default + display; sampled_at is stored UTC.

function tzParts(tz: string, date: Date): Record<string, string> {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  const out: Record<string, string> = {}
  for (const part of fmt.formatToParts(date)) {
    if (part.type !== 'literal') out[part.type] = part.value
  }
  if (out.hour === '24') out.hour = '00' // some engines emit 24 at midnight
  return out
}

// The current wall-clock in `tz` as a datetime-local value (no UTC shift).
export function nowInTz(tz: string): string {
  const p = tzParts(tz, new Date())
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

// The signed offset (ms) of `tz` at `date`: (wall-clock-as-UTC) - actual UTC.
function tzOffsetMs(tz: string, date: Date): number {
  const p = tzParts(tz, date)
  const asUtc = Date.UTC(
    Number(p.year),
    Number(p.month) - 1,
    Number(p.day),
    Number(p.hour),
    Number(p.minute),
    Number(p.second),
  )
  return asUtc - date.getTime()
}

// A datetime-local `value` (interpreted as a wall-clock in `tz`) -> UTC ISO.
export function wallclockToUtcIso(value: string, tz: string): string {
  const naiveUtc = new Date(`${value}:00Z`).getTime()
  const off = tzOffsetMs(tz, new Date(naiveUtc))
  return new Date(naiveUtc - off).toISOString()
}

// A stored UTC ISO -> datetime-local value in `tz` (edit-form prefill).
export function utcToTzInput(iso: string, tz: string): string {
  const p = tzParts(tz, new Date(iso))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

// A stored UTC ISO -> human display in `tz`.
export function utcToTzDisplay(iso: string, tz: string, locale = 'tr'): string {
  return new Date(iso).toLocaleString(locale, { timeZone: tz })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/utils/labTime.test.ts`
Expected: PASS (5 passed).

- [ ] **Step 5: Add the client functions**

In `scada-reporter/frontend/src/api/client.ts`, add (hand-written axios style):

```ts
export const getAppSettings = () => api.get<{ timezone: string }>('/settings')
export const updateTimezone = (timezone: string) =>
  api.put<{ timezone: string }>('/settings/timezone', { timezone })
```

- [ ] **Step 6: Create the hook**

Create `scada-reporter/frontend/src/hooks/useTimezone.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { getAppSettings } from '../api/client'

// The facility-global timezone (default Europe/Istanbul while loading / on error).
export function useTimezone(): string {
  const { data } = useQuery({
    queryKey: ['app-settings'],
    queryFn: () => getAppSettings(),
    staleTime: 5 * 60 * 1000,
  })
  return data?.data?.timezone ?? 'Europe/Istanbul'
}
```

- [ ] **Step 7: Typecheck + commit**

Run (from `scada-reporter/frontend`): `pnpm tsc -b` (0 errors), `pnpm lint` (clean on these files).

```bash
git checkout master
git add scada-reporter/frontend/src/utils/labTime.ts scada-reporter/frontend/src/utils/labTime.test.ts scada-reporter/frontend/src/hooks/useTimezone.ts
git commit -m "feat(lab): timezone helpers + app-settings client + useTimezone hook" -- scada-reporter/frontend/src/utils/labTime.ts scada-reporter/frontend/src/utils/labTime.test.ts scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/hooks/useTimezone.ts
```
(`client.ts` is tracked — no `git add` needed; footer in message.)

---

## Task 3: Apply the timezone in lab entry + Settings card

**Files:**
- Modify: `scada-reporter/frontend/src/pages/lab/SingleSampleTab.tsx`
- Modify: `scada-reporter/frontend/src/pages/lab/BatchTab.tsx`
- Modify: `scada-reporter/frontend/src/pages/lab/RecordsTab.tsx`
- Modify: `scada-reporter/frontend/src/pages/Settings.tsx`
- Modify: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/lab.json`
- Test: extend `scada-reporter/frontend/src/utils/labTime.test.ts` is already done; no new pure test here (UI wiring) — rely on `tsc -b` + `pnpm lint` + the Task 4 E2E.

**Interfaces:**
- Consumes: Task 2 `nowInTz`, `wallclockToUtcIso`, `utcToTzInput`, `utcToTzDisplay`, `useTimezone`, `updateTimezone`, `getAppSettings`.

- [ ] **Step 1: SingleSampleTab — default + save in tz**

In `scada-reporter/frontend/src/pages/lab/SingleSampleTab.tsx`:
- Add imports: `import { useTimezone } from '../../hooks/useTimezone'` and `import { nowInTz, wallclockToUtcIso } from '../../utils/labTime'`.
- Add `const tz = useTimezone()` in the component.
- Change the `sampledAt` initial state from `new Date().toISOString().slice(0, 16)` to `nowInTz(tz)`. (Because `tz` may resolve after first render, also add an effect to reset the default once when the field is still empty/at-mount default — simplest: initialize with `nowInTz('Europe/Istanbul')` and add `useEffect(() => setSampledAt(nowInTz(tz)), [tz])` guarded so it only overwrites the prefilled default, not user input; track a `touched` flag set on the input's `onChange`.)
- In the save call, replace `sampled_at: new Date(sampledAt).toISOString()` with `sampled_at: wallclockToUtcIso(sampledAt, tz)`.

Concretely, the default + reset:
```tsx
const tz = useTimezone()
const [sampledAt, setSampledAt] = useState(() => nowInTz('Europe/Istanbul'))
const [touched, setTouched] = useState(false)
useEffect(() => {
  if (!touched) setSampledAt(nowInTz(tz))
}, [tz, touched])
```
and the input gets `onChange={(e) => { setTouched(true); setSampledAt(e.target.value) }}`; the save uses `wallclockToUtcIso(sampledAt, tz)`.

- [ ] **Step 2: BatchTab — default rows + save in tz**

In `scada-reporter/frontend/src/pages/lab/BatchTab.tsx`:
- Add `import { useTimezone } from '../../hooks/useTimezone'` and `import { nowInTz, wallclockToUtcIso } from '../../utils/labTime'`; `const tz = useTimezone()`.
- The new-row factory `{ sampled_at: new Date().toISOString().slice(0, 16), values: {} }` becomes `{ sampled_at: nowInTz(tz), values: {} }`.
- The submit mapping `sampled_at: new Date(r.sampled_at).toISOString()` becomes `sampled_at: wallclockToUtcIso(r.sampled_at, tz)`.

- [ ] **Step 3: RecordsTab — display + edit in tz**

In `scada-reporter/frontend/src/pages/lab/RecordsTab.tsx`:
- Add `import { useTimezone } from '../../hooks/useTimezone'` and `import { utcToTzInput, utcToTzDisplay, wallclockToUtcIso } from '../../utils/labTime'`; `const tz = useTimezone()`; the page already has `useTranslation('lab')` → use its `i18n.language` for the display locale (or pass `'tr'`).
- Replace the existing local `toLocalDatetime(iso)` helper usage (edit-form prefill) with `utcToTzInput(s.sampled_at, tz)`.
- The list cell `new Date(s.sampled_at).toLocaleString()` becomes `utcToTzDisplay(s.sampled_at, tz, i18n.language)`.
- The edit save `sampled_at: new Date(editing.sampled_at).toISOString()` becomes `sampled_at: wallclockToUtcIso(editing.sampled_at, tz)`.
- If the local `toLocalDatetime` becomes unused, remove it.

- [ ] **Step 4: Settings — admin Timezone card**

Add a `TimezoneCard` to `scada-reporter/frontend/src/pages/Settings.tsx`, rendered (like the existing `LabCatalogCard`) behind `user?.role === 'admin'`. Implement it inline or as `src/pages/SettingsTimezoneCard.tsx`:
- Load the current value with `getAppSettings()` (or `useQuery(['app-settings'])`), render a `<select>` of `['Europe/Istanbul','UTC','Europe/London','Europe/Berlin','Europe/Moscow','Asia/Dubai']`, and on change call `updateTimezone(value)` then `queryClient.invalidateQueries({ queryKey: ['app-settings'] })` (use `useQueryClient`). Show a saved/﻿error state.
- All visible strings via i18n. Add keys to all 5 `lab.json` (the lab namespace is already imported by Settings via `LabCatalogCard`, so reuse it): `tz_title` ("Timezone"/"Saat Dilimi"), `tz_subtitle`, `tz_saved`. (Zone names themselves are not translated.)

- [ ] **Step 5: Verify**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/utils/labTime.test.ts` (still 5 pass), `pnpm tsc -b` (0 errors), `pnpm lint` (clean on changed files).

- [ ] **Step 6: Commit**

```bash
git checkout master
git commit -m "feat(lab): apply configurable timezone to entry/records + Settings card" -- scada-reporter/frontend/src/pages/lab/SingleSampleTab.tsx scada-reporter/frontend/src/pages/lab/BatchTab.tsx scada-reporter/frontend/src/pages/lab/RecordsTab.tsx scada-reporter/frontend/src/pages/Settings.tsx scada-reporter/frontend/src/i18n/locales/en/lab.json scada-reporter/frontend/src/i18n/locales/tr/lab.json scada-reporter/frontend/src/i18n/locales/ru/lab.json scada-reporter/frontend/src/i18n/locales/de/lab.json scada-reporter/frontend/src/i18n/locales/ar/lab.json
```
(plus `scada-reporter/frontend/src/pages/SettingsTimezoneCard.tsx` in the pathspec if you created it; footer in the message.)

---

## Task 4: End-to-end verification + docs

**Files:**
- Modify: `docs/lab-data-entry.md`

- [ ] **Step 1: Full backend suite + checks**

Run (from `scada-reporter/backend`): `just test` (includes `test_app_settings.py`). Then from repo root `just check` — confirm no NEW failure traces to this feature (a pre-existing non-lab bandit B608 may remain — out of scope).

- [ ] **Step 2: Manual E2E (browser)** — the backend must be restarted to load the new endpoint + migration applied (NSSM `EkontBackend` has no hot-reload; restart needs elevation; run `just migrate` first).
1. Settings (as admin): the Timezone card shows `Europe/Istanbul`.
2. Lab Data Entry → Single Sample: the default date/time matches the Turkey wall clock (not 3h behind).
3. Save a sample; Records tab shows the same wall-clock time.
4. Settings → change to `UTC`; reload Lab Data Entry → the default + records now show UTC wall-clock.

- [ ] **Step 3: Doc + commit/push**

Add a short "Timezone" note to `docs/lab-data-entry.md`: lab entry/records use a facility-global timezone (default `Europe/Istanbul`) set by an admin on the Settings page (`GET /api/settings`, `PUT /api/settings/timezone`); `sampled_at` is stored UTC and rendered in the configured zone.

```bash
git checkout master
git commit -m "docs(lab): document the configurable timezone setting" -- docs/lab-data-entry.md
git push origin master
```

---

## Self-Review

**Spec coverage:**
- IANA timezone, default Europe/Istanbul → Task 1 (`DEFAULT_TIMEZONE`, `zoneinfo` validation) + Task 3 (dropdown). ✓
- Backend-global storage, admin-set → Task 1 (`AppSetting` + `GET`/`PUT` with `require_role("admin")`). ✓
- Applied to lab entry default + save + record display → Task 3. ✓
- `sampled_at` stays UTC → `wallclockToUtcIso` stores UTC; display via `utcToTz*`. ✓
- Hook `useTimezone` + client → Task 2. ✓
- Tests: backend endpoint (default/upsert/422/403) + frontend pure helpers (round-trip) → Tasks 1 & 2. ✓
- Settings card admin-only → Task 3 Step 4. ✓
- Out-of-scope (Grafana panel tz, app-wide display tz) → not in any task. ✓

**Placeholder scan:** No "TBD". Task 3's component wiring is prose + exact replacement snippets (the files are large and the implementer must match existing JSX); the testable logic lives in Task 2's pure helpers with full code + tests.

**Type consistency:** `nowInTz(tz)`, `wallclockToUtcIso(value, tz)`, `utcToTzInput(iso, tz)`, `utcToTzDisplay(iso, tz, locale?)` defined in Task 2 and consumed with the same signatures in Task 3. `getAppSettings()`/`updateTimezone(tz)` return `AxiosResponse` (callers read `.data`), consistent with `useTimezone` reading `data?.data?.timezone`. Endpoint shapes (`{"timezone": str}`) match between Task 1 and the client/hook. Migration `down_revision="a1b2c3d4e5f7"` matches the verified head; new head `b2c3d4e5f6a8`.
