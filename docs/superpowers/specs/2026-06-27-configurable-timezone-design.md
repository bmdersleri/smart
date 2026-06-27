# Configurable Timezone for Lab Data Entry — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming) → ready for implementation plan

## Problem

Lab data entry records the wrong time. The datetime-local default is computed
with `new Date().toISOString()` (UTC), so in Turkey (UTC+3) the prefilled time
is ~3 hours behind the operator's wall clock, and the display round-trip loses
the offset. The fix must be **parametric**: a single facility-wide timezone,
configurable by an admin from the Settings page, applied to lab entry and
display.

## Requirements (from brainstorming)

- **Representation:** an IANA timezone name (e.g. `Europe/Istanbul`), chosen from
  a dropdown. Default `Europe/Istanbul`. (IANA handles DST via the `Intl` API.)
- **Storage:** a **backend-global** setting (one value for all operators/devices),
  set by an admin. Not a per-browser preference.
- **Applied to:** lab data entry (default time + save) and lab record display.
  The Grafana dashboard panel timezone and an app-wide display timezone are out
  of scope.
- `sampled_at` continues to be stored as UTC (consistent with the rest of the
  backend); the configured timezone governs how the operator enters and reads it.

## Architecture

### Backend — app settings store

**Model** `app/models/app_setting.py` — a generic key/value table:

```
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str]   = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
```

Registered in `app/main.py`'s `# noqa: F401` model-import block; created by an
Alembic migration (down_revision = current head).

**Router** `app/api/app_settings.py` (prefix `/settings`):

- `GET /settings` — any authenticated user → `{"timezone": <stored value or
  default "Europe/Istanbul">}`. Reads the `AppSetting` row with key `"timezone"`.
- `PUT /settings/timezone` — `require_role("admin")` + `require_writable` →
  body `{"timezone": str}`. Validates against `zoneinfo.available_timezones()`
  (HTTP 422 on an unknown zone), upserts the `timezone` `AppSetting` row, returns
  `{"timezone": <value>}`.

Default constant `DEFAULT_TIMEZONE = "Europe/Istanbul"`. Registered in `main.py`.

### Frontend — fetch + apply

**Client** (`src/api/client.ts`, hand-written axios):
- `getAppSettings()` → `api.get<{timezone: string}>('/settings')`
- `updateTimezone(timezone: string)` → `api.put<{timezone: string}>('/settings/timezone', { timezone })`

**Timezone hook** `src/hooks/useTimezone.ts` — fetches `GET /settings` once
(TanStack Query, the project's data layer) and returns the configured timezone,
falling back to `"Europe/Istanbul"` while loading or on error. (A thin wrapper
so lab components don't each refetch.)

**Settings page** (`src/pages/Settings.tsx`) — an admin-only "Saat Dilimi"
(Timezone) card: a `<select>` of a curated IANA list (`Europe/Istanbul`, `UTC`,
`Europe/London`, `Europe/Berlin`, `Europe/Moscow`, `Asia/Dubai`) bound to the
current value (from `getAppSettings`), saving via `updateTimezone` and
invalidating the query. Rendered behind `user?.role === 'admin'` like the
existing License/Lab-Catalog cards.

**Timezone helpers** `src/utils/labTime.ts` — pure, unit-tested, using
`Intl.DateTimeFormat` with `timeZone`:

- `nowInTz(tz): string` — the current wall-clock in `tz` as `"YYYY-MM-DDTHH:mm"`
  (the datetime-local default — no longer UTC).
- `wallclockToUtcIso(value, tz): string` — interpret a datetime-local `value`
  (`"YYYY-MM-DDTHH:mm"`) as a wall-clock in `tz` and return the UTC instant as an
  ISO string (`…Z`) for the API.
- `utcToTzInput(iso, tz): string` — a stored UTC ISO → `"YYYY-MM-DDTHH:mm"` in
  `tz` (edit-form prefill).
- `utcToTzDisplay(iso, tz, locale): string` — a stored UTC ISO → a human-readable
  string in `tz` (record list).

Internals use a small `_tzParts(tz, date)` (via `formatToParts`) and a
`_tzOffsetMs(tz, date)` derived from it; for fixed-offset zones (Turkey +03) the
conversion is exact, and near a DST boundary the 1-hour ambiguity is acceptable
for manual lab entry.

### Wiring

- `SingleSampleTab.tsx` + `BatchTab.tsx`: read `tz` from `useTimezone()`; default
  `sampledAt`/row time = `nowInTz(tz)`; on save send `wallclockToUtcIso(value, tz)`
  instead of `new Date(value).toISOString()`.
- `RecordsTab.tsx`: list display via `utcToTzDisplay(s.sampled_at, tz, lang)`;
  edit-form prefill via `utcToTzInput`; edit save via `wallclockToUtcIso`.

## Testing (TDD)

- **Backend** (`tests/test_app_settings.py`): `GET /settings` returns the default
  `Europe/Istanbul` when unset and the stored value when set; `PUT
  /settings/timezone` as admin upserts + returns it; an invalid zone → 422; a
  non-admin → 403; the model round-trips.
- **Frontend** (`src/utils/labTime.test.ts`, vitest): with `tz="Europe/Istanbul"`
  (fixed +03), `wallclockToUtcIso("2026-06-27T12:00","Europe/Istanbul")` ===
  `"2026-06-27T09:00:00.000Z"`; `utcToTzInput("2026-06-27T09:00:00Z",
  "Europe/Istanbul")` === `"2026-06-27T12:00"` (round-trip); `nowInTz("UTC")` vs
  `nowInTz("Europe/Istanbul")` differ by the offset; `utcToTzDisplay` contains the
  +03 wall-clock. (These are deterministic regardless of the CI machine's local
  zone because they pin an explicit IANA zone.)

## Verification

After implementation: in Settings (as admin) confirm the Timezone card; in Lab
Data Entry confirm the default time matches the Turkey wall clock (not 3h
behind); save a sample and confirm the Records tab shows the same wall-clock;
change the setting to `UTC` and confirm the lab default/display shift
accordingly.

## Out of scope (YAGNI)

- Grafana dashboard panel timezone (separate concern; the complaint was the
  entry section).
- An app-wide display timezone for non-lab pages (they keep browser-local).
- Per-user timezone preferences (the setting is facility-global by decision).
