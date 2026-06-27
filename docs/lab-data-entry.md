# Lab Data Entry & Tracking

Manual entry of laboratory analysis and measurement results into the EKONT SMART REPORT system.

## Purpose

SCADA/PLC data is ingested automatically, but laboratory results (pH, COD, TSS,
turbidity, etc.) are produced by lab staff and must be entered manually. This
feature provides:

- A dedicated **Lab Data Entry** screen in the web UI.
- Lab data tracked on Grafana dashboards alongside existing SCADA time-series.
- Reuse of the existing **Advanced Reports** engine (no new generator code) via
  optional mirroring of lab values into `tag_readings`.

---

## Entry Modes

The Lab Data Entry page has four tabs.

### 1. Single Sample

Fill in sample point (combobox with "+ new" to create on the fly), date/time
(defaults to now), optional method/batch/note, then enter values for each
parameter. Values outside the catalog min/max limits are flagged red immediately
in the UI. Save calls `POST /api/lab/samples`.

### 2. Batch Table

A grid where each row is a sample-time and each column is a parameter. Select
parameter columns, fill cells, add/remove rows, then **Save All** sends all rows
in a single call to `POST /api/lab/samples/batch`. Useful for entering a session
of measurements at once.

### 3. Excel / CSV Import

Upload an Excel (`.xlsx`, `.xls`) or CSV file. The server reads the file and
returns headers plus a column-to-parameter mapping suggestion (matched
case-insensitively against the catalog). Review the mapping, optionally override
it, preview up to 200 rows, then click **Import** to call
`POST /api/lab/import/commit`. The response reports `{inserted, errors}` with
per-row error tolerance (bad rows are skipped, good rows are committed).

### 4. Records (Edit / Delete)

Paginated list of all samples with filters for sample point, parameter, date
range, and operator. Rows for which the current user is authorized (admin or
record owner) show **Edit** and **Delete** actions. Edit opens a single-sample
form modal. Delete is permanent and audited.

---

## Hybrid Catalog

The catalog consists of two entity types managed from **Settings → Lab Catalog**
(admin only):

- **Parameters** (`lab_parameters`): measurement types (code, name, unit,
  category, min/max limits, mirror target).
- **Sample Points** (`lab_sample_points`): physical or virtual sampling locations
  (code, name, description).

**Operator-added entries** — When an operator selects "+ new" in the entry form,
a new parameter or sample point is created with `approved = false`. These are
visible in the catalog card as a pending list. An admin approves (or deletes)
them via `PATCH /api/lab/parameters/{id}` with `{"approved": true}`.

Admin-created entries default to `approved = true` immediately.

---

## Mirror to Tag Readings (`mirror_to_tag_id`)

Each `lab_parameter` has an optional `mirror_to_tag_id` (FK → `tags.id`). When
set, every time a sample is saved the API writes the measured numeric value into
`tag_readings` (with `quality=192` and `timestamp=sampled_at`) in the same
transaction.

**Effect:** mirrored lab parameters appear on existing SCADA Grafana dashboards
and panels as if they were a regular tag, enabling direct comparison on the same
time-series panel. They are also selectable in **Advanced Reports** — statistics,
PDF, Excel, and embedded Grafana panels all work with no additional code.

Note: mirror writes happen only on the initial sample creation (`POST`). Editing
a sample (`PATCH`) updates the `lab_measurements` rows but does not re-apply the
mirror write.

---

## `v_lab_timeseries` SQL View

The Alembic migration (revision `a1b2c3d4e5f7`) creates:

```sql
CREATE VIEW v_lab_timeseries AS
SELECT
    ls.sampled_at  AS time,
    sp.code        AS point_code,
    lp.code        AS param_code,
    lp.name        AS param_name,
    lp.unit        AS unit,
    lm.value       AS value,
    lp.min_limit   AS min_limit,
    lp.max_limit   AS max_limit
FROM lab_measurements lm
JOIN lab_samples ls       ON ls.id = lm.sample_id
JOIN lab_parameters lp    ON lp.id = lm.parameter_id
JOIN lab_sample_points sp ON sp.id = ls.sample_point_id
WHERE lm.value IS NOT NULL
```

Grafana dashboards query this view through the TimescaleDB/PostgreSQL datasource.

**SQLite-dev caveat:** The view is created on SQLite during tests (the same SQL
is portable). However, the **Grafana lab-quality dashboard requires a
PostgreSQL/TimescaleDB datasource** — it will not work against the SQLite dev
database. Use `just docker-up` to start TimescaleDB for full Grafana testing.

---

## Grafana Lab Quality Dashboard

A provisioned dashboard is located at:

```
scada-reporter/docker/grafana/dashboards/lab-quality.json
```

It is automatically copied into the Grafana service provisioning folder by
`configure-grafana-windows-service.ps1`.

The dashboard provides:

- **Template variables** — `point` (sample point code) and `param` (parameter
  code), populated from `v_lab_timeseries`.
- **Time-series panel** — lab values over the selected time range, with
  horizontal threshold lines at `min_limit` and `max_limit`.
- **Latest-values table** — most recent measurement per parameter for the
  selected sample point.

---

## Permissions

| Action | Who |
|--------|-----|
| View samples and catalog | All authenticated users |
| Enter samples (single / batch / import) | `operator` + `admin` |
| Edit a sample | `admin` OR the `entered_by` user of that record |
| Delete a sample | `admin` OR the `entered_by` user of that record |
| Add a catalog entry (parameter / sample point) | `operator` + `admin` (lands `approved=false` for operators) |
| Approve / update / delete catalog entries | `admin` only |

Edit and delete operations are **audited** — they write to `audit_log` with
actions `lab.sample.update` and `lab.sample.delete` respectively (visible via
`GET /api/audit`).

**License:** no new feature gate. Demo mode (read-only) blocks all write
operations through the existing `require_writable` dependency.

---

## API Endpoints (`/api/lab`)

### Catalog

| Method | Path | Description |
|--------|------|-------------|
| GET | `/lab/parameters` | List parameters (optional `?approved=` / `?active=` filters) |
| POST | `/lab/parameters` | Create parameter (operator/admin; operators land `approved=false`) |
| PATCH | `/lab/parameters/{id}` | Update parameter, including setting `approved=true` (admin) |
| DELETE | `/lab/parameters/{id}` | Delete parameter (admin) |
| GET | `/lab/sample-points` | List sample points |
| POST | `/lab/sample-points` | Create sample point |
| PATCH | `/lab/sample-points/{id}` | Update sample point (admin) |
| DELETE | `/lab/sample-points/{id}` | Delete sample point (admin) |

### Samples

| Method | Path | Description |
|--------|------|-------------|
| POST | `/lab/samples` | Single sample entry |
| POST | `/lab/samples/batch` | Batch row entry `{rows:[...]}` |
| GET | `/lab/samples` | List/filter samples (point, parameter, date, operator) + pagination |
| GET | `/lab/samples/{id}` | Get a single sample with measurements |
| PATCH | `/lab/samples/{id}` | Edit sample (admin or owner, audited) |
| DELETE | `/lab/samples/{id}` | Delete sample (admin or owner, audited) |

### Import

| Method | Path | Description |
|--------|------|-------------|
| POST | `/lab/import/preview` | Upload file → header mapping suggestions + row preview |
| POST | `/lab/import/commit` | Apply mapping → bulk import; returns `{inserted, errors}` |

---

## Data Model

Four tables in the migration `a1b2c3d4e5f7`:

- **`lab_parameters`** — measurement type catalog.
- **`lab_sample_points`** — sampling location catalog.
- **`lab_samples`** — one sample event (point + time + operator + metadata).
- **`lab_measurements`** — one row per parameter value within a sample (cascade
  delete from `lab_samples`).

A single-measurement entry is a `lab_sample` with one `lab_measurement` row —
the same unified model covers both single and multi-parameter samples.
