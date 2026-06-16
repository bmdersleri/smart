# Excel Template Fill — Design Spec

**Date:** 2026-06-16
**Status:** Approved, pending implementation plan
**Scope:** Sub-project A (branded template-fill). Sub-project B (ad-hoc config reports) deferred to its own spec.

## Problem

Operators maintain branded monthly operational logs in Excel (e.g. `gunluk_rapor.xlsx`): one sheet per month, header rows naming plants + sensor codes (`410BF103`, `460BF105`...), then a daily grid — one row per day, columns = daily sensor values (debi m³/gün, elektrik tüketimi kWh, çamur değerleri, etc.). Today these are filled by hand.

Goal: let the system **fill these branded templates automatically** from collected SCADA data — preserving the exact layout, logos, formats, and formulas — by mapping each data column to a PLC tag and writing daily aggregates.

This is distinct from ad-hoc reporting (sub-project B), which generates Excel from scratch via config. A = "fill my existing branded Excel"; B = "configure a generated Excel". Both read the same daily-rollup primitive.

## Decisions (from brainstorming)

- **Approach:** A first (new, hard), B later (extends existing `excel_builder.py`).
- **Mapping:** hybrid — auto-detect column→tag from the embedded sensor-code row, user confirms/corrects and saves.
- **Data source:** new `tag_readings_1d` continuous aggregate, long retention. Per-column agg ∈ {sum, avg, min, max, last, delta}. `delta` = last − first reading of the day (for cumulative counters → daily consumption).
- **Fill target:** clean single-sheet template in → fresh monthly `.xlsx` out. Master 60-sheet workbook stays untouched as the human archive.
- **Row mapping:** auto-detect `TARİH` column + grid start; one row per day of selected month.
- **No backfill:** system fills only data it actually collected (≈ from 2026-06 onward). Pre-existing historical months stay manual.

## Architecture

New module `app/services/template_fill/`.

| Unit | Purpose | Depends on |
|------|---------|-----------|
| `daily_rollup` (migration + `daily_values()`) | `tag_readings_1d` continuous aggregate: per tag/day → avg/min/max/sum/count. Long retention. Single query interface degrading to SQLite. | timescaledb, tag_readings |
| `template_inspector.py` | Load `.xlsx`, detect sheet/header row/date col/grid start. Propose column→tag mapping (sensor code → `tag.name`) + agg guesses + unmapped/formula cols. | openpyxl, Tag |
| `ExcelTemplate` + `ExcelTemplateColumn` models | Persist confirmed layout + per-column mapping. | DB |
| `fill_engine.py` | Given template + (year, month): load clean template blob, write date + daily values per mapped column, preserve styles, return bytes. | inspector, daily_rollup, openpyxl |
| `api/excel_templates.py` | REST: inspect, save mapping, generate→download, list, delete. | above |

**Flow:** upload → auto-detect → user confirms mapping + agg → save → generate(month) → xlsx out.

## Data Model

### `excel_templates`
One row per registered template layout.

| Column | Type | Note |
|--------|------|------|
| `id` | int PK | |
| `name` | str unique | "Balta Aylık Operasyon" |
| `description` | text | |
| `file_blob` | LargeBinary | clean 1-sheet `.xlsx`; source of truth for fills |
| `sheet_name` | str | target sheet |
| `header_row` | int | row holding sensor codes (`SENSÖR KODLARI`) |
| `date_col` | str | e.g. `"D"` |
| `data_start_row` | int | first day row |
| `date_mode` | str | `match` (dates pre-seeded) \| `write` (system writes dates) |
| `created_at` / `created_by` / `updated_at` | | mirror `report_template` |

### `excel_template_columns`
Per mapped column (1:N, cascade delete).

| Column | Type | Note |
|--------|------|------|
| `id` | int PK | |
| `template_id` | FK → excel_templates (cascade) | |
| `col_letter` | str | `"E"` |
| `tag_id` | FK → tags (SET NULL) | null = unmapped/manual → skip on fill |
| `agg` | str | `sum\|avg\|min\|max\|last\|delta` |
| `source_code` | str | sensor code auto-detected; for drift re-check |
| `enabled` | bool | toggle off without deleting |

Rationale: blob in DB (not FS path) → template self-contained, matches `report_archive.result_json` pattern. Unmapped/weather columns have no row → fill leaves them blank.

## Daily Rollup

Extends the existing CAGG pattern (`core/timescaledb.py:64`). Current rollups store `avg/min/max/n`; daily adds `sum`:

```sql
CREATE MATERIALIZED VIEW tag_readings_1d WITH (timescaledb.continuous) AS
SELECT tag_id, time_bucket('1 day', timestamp) AS bucket,
       avg(value) AS avg, min(value) AS min, max(value) AS max,
       sum(value) AS sum, count(*) AS n
FROM tag_readings GROUP BY tag_id, bucket WITH NO DATA;
```

- **No `last`/`first` in the CAGG** — Timescale restricts those in continuous aggregates. CAGG covers `avg/min/max/sum`. When a column's agg = `last`, `fill_engine` runs a separate `DISTINCT ON (tag_id) ... ORDER BY timestamp DESC` per day. `delta` reads both ends per day (`first` via `ORDER BY timestamp ASC`, `last` via `DESC`) → `last − first`; null if either end missing.
- **Long retention** — no retention policy on `tag_readings_1d` (raw stays 7d). Daily rows are tiny; years fit. Enables any collected past month.
- **Refresh policy** — wide `start_offset`, `end_offset '1 hour'` so the current day stays fresh.

**Single query interface** — `daily_values(tag_id, year, month, agg) -> {date: value}`:
- PG/Timescale → read `tag_readings_1d` (or `DISTINCT ON` for `last`/`delta`).
- SQLite dev (no timescale) → `GROUP BY date(timestamp)` straight on `tag_readings`, same agg funcs. Mirrors `dashboard._query_rollup` degradation.

Day boundaries computed in plant-local time, not UTC.

## Fill Engine + Auto-Detect

### Auto-detect (`template_inspector`) — heuristics, all overridable
- **Sensor-code row:** scan first ~6 rows, pick the row with most cells matching tag-code regex (`^\d{3}[A-Z]{2}\d{3}$`), cross-checked vs DB `tag.name` → `header_row`.
- **Date column:** header cell text ≈ `TARİH` (TR-normalized) → `date_col`.
- **Grid start row:** first row below header where date col holds a date; for `write` mode, first empty data row.
- **Column→tag proposal:** exact match code → `tag.name`. No match → unmapped. Default `agg` guessed from label: `m³/gün`/`DEBİ` → `sum`; `TÜKETİM`/`SAYAÇ`/cumulative kWh → `delta`; `%`/`ORAN` → `avg`; level/`SEVİYE` → `last`; else `avg`.

### Fill (`fill_engine.fill(template_id, year, month) -> bytes`)
1. Load `file_blob` via openpyxl (`data_only=False` → keep formulas).
2. Resolve target sheet; days = 1..N of month.
3. Per mapped+enabled column: `vals = daily_values(tag_id, year, month, agg)`.
4. Per day → row:
   - `write` mode → row = `data_start_row + (day-1)`; write date into `date_col`.
   - `match` mode → locate row whose date col == that day (no contiguity assumption).
   - Write `vals.get(day)` into `col_letter+row`. Missing day → blank (no fabricated 0).
5. Preserve existing cell number-format/style — write value only, never restyle.
6. Save to BytesIO → return bytes. Archive via `report_archive`; download via API.

### Edge cases

| Case | Handling |
|------|----------|
| Day has no data | blank cell, not 0 |
| Tag deleted (`tag_id` null) | skip column |
| Template edited, codes shifted | re-detect compares `source_code`; warn drift, block fill until reconfirm |
| Merged cells in grid | write to top-left anchor only |
| `last` / `delta` agg | separate `DISTINCT ON` query path; `delta` = last − first, null if either end missing |
| Month partly collected | fill available days, rest blank |
| `match` mode, date missing | skip that day, log |
| Formula cells | inspector flags formula cols as non-fillable; never overwrite |

Values written raw (float); template's own cell format renders units/decimals.

## Frontend

New page `pages/ExcelTemplates.tsx` (sidebar "Excel Şablonları"), three views via local state.

**List:** table of templates (name, sheet, #mapped cols, last generated, actions: Generate / Edit mapping / Delete). "+ Şablon Yükle".

**Upload + mapping confirm (core UI):**
- Step 1: drag-drop `.xlsx` + name → POST `/excel-templates/inspect` (multipart); backend returns proposal, no save.
- Step 2: mapping grid, one row per detected column:

  | Col | Detected label | Sensor code | → Tag (searchable select) | Agg | Enabled |
  |-----|----------------|-------------|---------------------------|-----|---------|
  | E | TESİSE ALINAN DEBİ | 410BF103 | 410BF103 ✓ auto | sum | ☑ |
  | B | HAVA DURUMU | — | (unmapped) | — | ☐ |

  - Auto-matched rows pre-filled + "auto" badge; unmatched highlighted.
  - Tag select reuses existing tag picker. Agg dropdown: sum/avg/min/max/last/delta.
  - Editable header_row / date_col / data_start_row / date_mode / sheet (detected values shown).
- "Kaydet" → POST `/excel-templates`.

**Generate:** "Oluştur" → modal month/year picker (default current) → POST `/excel-templates/{id}/generate?year=&month=` → xlsx download; appears in report history. Drift banner if `source_code` mismatch → reopen mapping.

Reuse tag picker, modal, `useSortable`, TanStack Query, OpenAPI client (`just gen-client`). Light/dark theme aware. No new design system.

## Testing (TDD, pytest async)

| Layer | Tests |
|-------|-------|
| `daily_values` | SQLite path sum/avg/min/max/last/delta correct; delta = last−first; delta null on single/missing reading; missing-day gaps; tz day boundaries |
| `template_inspector` | code-row detect; `TARİH` find; agg guess; exact tag match; unmatched → unmapped; formula-col flag |
| `fill_engine` | write mode dates+values; match mode existing dates; blank on missing (not 0); merged-cell anchor; skip null tag; format preserved; `last` path |
| API | inspect multipart → proposal; save round-trips; generate → valid xlsx bytes; drift detection |

Fixture: tiny hand-built 1-sheet `.xlsx` (3 cols, 5 days), not the 9.5MB real file. Assertions re-open generated xlsx with openpyxl and verify cells. Frontend: vitest on mapping-grid state.

## Scope Cuts (YAGNI)
- No backfill of pre-collection historical months.
- No template chart generation (template's own images/format only).
- No in-place master-workbook edit.
- No `{{token}}` substitution engine (grid-fill only).
- No PDF for A v1 (xlsx only).

## Build Order
1. `tag_readings_1d` rollup + `daily_values` interface (+ migration)
2. `template_inspector` (auto-detect)
3. `ExcelTemplate` / `ExcelTemplateColumn` models (+ migration)
4. `fill_engine`
5. API endpoints
6. Frontend page
7. Wire archive/history + drift detection

## Sub-project B (deferred)
Extends `excel_builder.py` + `ReportTemplate`. UI-configured sections/columns, built from scratch, no external file. Reads the same `tag_readings_1d` rollup. Own spec/plan after A ships. **A unblocks B** (rollup is the shared primitive).
