# Advanced Reporting System — Implementation Plan

## Context

The current reporting system (`app/api/reports.py`) only does on-demand Excel/JSON generation with basic aggregation (avg/min/max/count) and caps history at 10 records (auto-evicting the oldest). The user wants a professional-grade reporting subsystem:

- **Report templates** — named, reusable report definitions with a rich editor
- **Scheduled reports** — automatic generation at intervals/cron from a template
- **Permanent archive** — every generated report stored and searchable (no 10-record cap)
- **Statistical engine** — std dev, percentiles, trend regression, availability/gap analysis
- **Anomaly detection** — z-score outliers, sudden jumps, alarm-threshold breaches, quality issues, surfaced in the report
- **Trend charts** — server-rendered line charts embedded in Excel/PDF with anomaly markers
- **PDF output** — professional WeasyPrint + Jinja2 reports

**Hard constraint:** The existing `/api/reports/*` endpoints and the `ReportHistory` model must stay **100% untouched** — the agent CLI depends on them. New work lives under `/api/advanced-reports` with new models.

**Compatibility:** Must remain SQLite-compatible (dev) while working on PostgreSQL/TimescaleDB (prod). APScheduler jobs must survive backend restarts.

Most packages needed are already in `requirements.txt` (unused today): `apscheduler>=3.11`, `pandas>=3.0`, `matplotlib>=3.11`, `weasyprint>=62.3`, `jinja2>=3.1`, `openpyxl>=3.1.5`, `python-docx>=1.2`, `reportlab>=4.5`, `plotly>=6.8`. `numpy 2.4.6` is installed transitively via pandas.

> **⚠️ scipy is NOT available** — not in `requirements.txt` and not installed in `.venv` (verified 2026-06-15). The original plan called `scipy.stats.linregress`. To avoid adding a heavy new dependency, the stats engine now uses **numpy only** (`numpy.polyfit` for the trend line + a manual R² computation). See §2.1.

---

## Codebase Reality Check (verified 2026-06-15)

The repo root for this project is **`C:\project\smart\scada-reporter\`** — backend at `scada-reporter/backend`, frontend at `scada-reporter/frontend`. All paths below are relative to those. (The line numbers cited for `main.py` / `alembic/env.py` were re-verified against the live files and still match.)

Confirmed against live code:
- `Tag` model has `min_alarm` / `max_alarm` (`Float`, nullable) — anomaly alarm checks work as planned. `Tag.created_at` still uses the legacy `datetime.utcnow` (not yet migrated); **new** models must use `datetime.now(UTC)`.
- `TagReading` columns: `tag_id`, `value` (nullable Float), `quality` (Integer, default 192), `timestamp`. Composite PK `(tag_id, timestamp)`. Matches the stats-engine tuple shape `(timestamp, value, quality)`.
- `main.py` (93 lines): imports L10, `ReportHistory` import L17, "tablolar hazir" L41, `yield` L59, router includes end L87 — all plan insertion points valid.
- `alembic/env.py`: model imports at L8–L10 — add the 3 new imports there.
- `reports.py` / `ReportHistory` / `_fetch_aggregated` (SQLite `strftime` agg) untouched as required.
- Frontend files exist: `src/api/client.ts`, `src/App.tsx`, `src/components/Layout.tsx`, `src/pages/{Reports,Tags,Trend,Dashboard}.tsx`.
- Dirs `app/services`, `app/schemas`, `app/templates` do **not** exist yet — all NEW.
- Tests: only `tests/test_api.py` today. New `stats_engine` unit tests go in `tests/`.

---

## Architecture Overview

```
                         POST /templates/{id}/run (manual)
                                      │
   APScheduler job ──────────────────┤
   (_run_scheduled_report)           ▼
                          ┌────────────────────────┐
                          │   report_generator     │  orchestrator
                          │ generate_report_from_  │
                          │      template()        │
                          └───────────┬────────────┘
                                      │ fetches raw TagReading rows
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
       stats_engine            chart_generator          (pandas resample
   compute_tag_stats()    generate_timeseries_chart()    for period rows)
   detect_anomalies()     generate_summary_bar_chart()
              │                       │
              └───────────┬───────────┘
                          ▼
            ┌─────────────┴──────────────┐
            ▼              ▼              ▼
      excel_builder    pdf_builder     json (gzip)
            └──────────────┬───────────────┘
                           ▼
                    ReportArchive row
                  (status, file_path, result_json)
```

The orchestrator fetches **raw** readings once per tag, then feeds the same in-memory series to the stats engine, anomaly detector, chart generator, and pandas-based period aggregation. One data fetch, many consumers.

---

## Part 1 — Database Models (3 new tables)

All three must be imported in `alembic/env.py` (same `# noqa: F401` pattern as `app.models.report_history` on line 8) **and** in `app/main.py` so `Base.metadata.create_all` picks them up at startup.

### 1.1 `app/models/report_template.py`

```python
from datetime import UTC, datetime   # UTC required for datetime.now(UTC) below
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[int]                         = mapped_column(Integer, primary_key=True)
    name: Mapped[str]                       = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str]                 = mapped_column(Text, default="")
    tag_ids: Mapped[str]                     = mapped_column(Text)             # JSON "[1,2,3]"
    time_range_type: Mapped[str]             = mapped_column(String(20), default="last_24h")
                                                # last_1h|last_24h|last_7d|last_30d|custom
    custom_start: Mapped[datetime | None]    = mapped_column(DateTime, nullable=True)
    custom_end: Mapped[datetime | None]      = mapped_column(DateTime, nullable=True)
    interval: Mapped[str]                    = mapped_column(String(20), default="hourly")
                                                # hourly|daily|weekly
    output_format: Mapped[str]               = mapped_column(String(10), default="excel")
                                                # excel|pdf|json
    # statistics toggles
    include_std_dev: Mapped[bool]            = mapped_column(Boolean, default=True)
    include_percentiles: Mapped[bool]        = mapped_column(Boolean, default=True)
    percentile_levels: Mapped[str]           = mapped_column(Text, default="[10,25,50,75,90,95]")
    include_trend_line: Mapped[bool]         = mapped_column(Boolean, default=True)
    # anomaly detection
    anomaly_enabled: Mapped[bool]            = mapped_column(Boolean, default=True)
    anomaly_zscore_threshold: Mapped[float]  = mapped_column(Float, default=3.0)
    # section visibility
    show_summary_stats: Mapped[bool]         = mapped_column(Boolean, default=True)
    show_trend_charts: Mapped[bool]          = mapped_column(Boolean, default=True)
    show_anomaly_table: Mapped[bool]         = mapped_column(Boolean, default=True)
    show_raw_data: Mapped[bool]              = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]             = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime]             = mapped_column(DateTime, default=lambda: datetime.now(UTC),
                                                             onupdate=lambda: datetime.now(UTC))
    created_by: Mapped[int | None]           = mapped_column(ForeignKey("users.id"), nullable=True)
```

> Note: use `datetime.now(UTC)` (not `utcnow()`) to match the timezone fix already applied in `s7_collector.py`.

### 1.2 `app/models/scheduled_report.py`

```python
class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id: Mapped[int]                         = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int]                = mapped_column(ForeignKey("report_templates.id", ondelete="CASCADE"))
    name: Mapped[str]                       = mapped_column(String(255))
    schedule_type: Mapped[str]              = mapped_column(String(20))       # cron|interval
    # cron fields (None = wildcard)
    cron_hour: Mapped[int | None]           = mapped_column(Integer, nullable=True)    # 0-23
    cron_minute: Mapped[int | None]         = mapped_column(Integer, nullable=True, default=0)
    cron_day_of_week: Mapped[str | None]    = mapped_column(String(20), nullable=True) # "mon"|"0,6"|None
    cron_day_of_month: Mapped[int | None]   = mapped_column(Integer, nullable=True)    # 1-31
    # interval field
    interval_hours: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    # APScheduler linkage + run tracking
    apscheduler_job_id: Mapped[str | None]  = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool]                 = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None]    = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None]     = mapped_column(String(20), nullable=True)  # completed|failed|running
    last_run_error: Mapped[str | None]      = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None]    = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=lambda: datetime.now(UTC))
```

### 1.3 `app/models/report_archive.py`

Replaces the capped `ReportHistory` for the new system. Keeps a full lifecycle (`pending → running → completed/failed`) plus a compressed JSON payload for preview/search.

```python
from datetime import UTC, datetime   # all 3 model files need UTC, datetime + their sqlalchemy cols
from sqlalchemy import Index, LargeBinary

class ReportArchive(Base):
    __tablename__ = "report_archive"

    id: Mapped[int]                          = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int | None]          = mapped_column(ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True)
    scheduled_report_id: Mapped[int | None]  = mapped_column(ForeignKey("scheduled_reports.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str]                      = mapped_column(String(20), default="pending")
                                                # pending|running|completed|failed
    trigger: Mapped[str]                     = mapped_column(String(20), default="manual")  # manual|scheduled
    created_at: Mapped[datetime]             = mapped_column(DateTime, default=lambda: datetime.now(UTC), index=True)
    started_at: Mapped[datetime | None]      = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None]    = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None]        = mapped_column(Text, nullable=True)
    tag_ids: Mapped[str]                     = mapped_column(Text)            # JSON "[1,2,3]"
    start: Mapped[datetime]                  = mapped_column(DateTime)        # data period start
    end: Mapped[datetime]                    = mapped_column(DateTime)        # data period end
    interval: Mapped[str]                    = mapped_column(String(20))
    output_format: Mapped[str]               = mapped_column(String(10))
    file_path: Mapped[str | None]            = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    result_json: Mapped[bytes | None]        = mapped_column(LargeBinary, nullable=True)  # gzip-compressed summary
    triggered_by: Mapped[int | None]         = mapped_column(ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("idx_report_archive_template_id", "template_id"),
        Index("idx_report_archive_status", "status"),
    )
```

### 1.4 Migration

Create `alembic/versions/<rev>_advanced_reporting.py` (via `alembic revision --autogenerate -m "advanced_reporting"` after the env.py imports are added, then review).

- Creates `report_templates`, `scheduled_reports`, `report_archive` with FK constraints + indexes.
- APScheduler's own `apscheduler_jobs` table is created automatically by `SQLAlchemyJobStore` at runtime — **not** part of this migration.
- Add 3 imports to `alembic/env.py` next to line 8–10:
  ```python
  import app.models.report_template   # noqa: F401
  import app.models.scheduled_report  # noqa: F401
  import app.models.report_archive    # noqa: F401
  ```

---

## Part 2 — Backend Services (`app/services/` — new package)

### 2.1 `stats_engine.py` — pure computation, no DB, no I/O

Input is always a list of `(timestamp, value, quality)` tuples so it is trivially unit-testable.

> **No scipy.** Trend regression uses `numpy.polyfit` + manual R²:
> ```python
> slope, intercept = np.polyfit(x, vals, 1)        # x = hours-from-start
> pred = slope * x + intercept
> ss_res = np.sum((vals - pred) ** 2)
> ss_tot = np.sum((vals - vals.mean()) ** 2)
> trend_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
> ```
> Guard `len(vals) < 2` (and `ss_tot == 0`, i.e. constant series) → `slope=None`/`r2=None`.

```python
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np

@dataclass
class TagStats:
    tag_id: int
    tag_name: str
    unit: str
    count: int                      # total readings in window
    good_quality_count: int         # quality == 192
    availability_pct: float         # good / total * 100
    avg: float | None
    std_dev: float | None
    variance: float | None
    min: float | None
    max: float | None
    percentiles: dict[int, float]   # {10: .., 25: .., 50: .., ...} per template.percentile_levels
    trend_slope: float | None       # units per hour (linregress)
    trend_r2: float | None          # r_value ** 2
    trend_direction: str            # rising|falling|stable
    rate_of_change_per_hour: float | None  # (last - first) / hours
    gap_count: int                  # gaps > 2 × expected interval
    gap_total_seconds: float

@dataclass
class AnomalyEvent:
    timestamp: datetime
    value: float | None
    anomaly_type: str   # zscore|jump|alarm_min|alarm_max|quality
    severity: str       # warning|critical
    details: str        # human-readable, e.g. "z=4.2 (mean=12.3, σ=1.1)"

def compute_tag_stats(
    readings: list[tuple[datetime, float | None, int]],
    tag_id: int, tag_name: str, unit: str,
    percentile_levels: list[int],
    expected_interval_seconds: int = 5,
) -> TagStats:
    """
    - Filter to good points: value is not None AND quality == 192
    - numpy: mean, std (ddof=1), var, min, max, np.percentile(vals, levels)
    - Trend: x = hours-from-start float array; np.polyfit(x, vals, 1) -> slope, intercept
        slope -> units/hour; trend_r2 = 1 - ss_res/ss_tot (manual, see note above)
        direction: rising if slope > 0.01*std/hr, falling if < -0.01*std/hr, else stable
    - rate_of_change: (vals[-1] - vals[0]) / total_hours
    - Gaps: sort timestamps, diff; count + sum diffs > 2*expected_interval_seconds
    - Guard: empty/1-point series -> None stats, direction "stable"
    """

def detect_anomalies(
    readings: list[tuple[datetime, float | None, int]],
    stats: TagStats, zscore_threshold: float,
    min_alarm: float | None, max_alarm: float | None,
) -> list[AnomalyEvent]:
    """
    - zscore: |v - mean| / std > threshold  -> severity critical if >1.5*threshold else warning
    - jump:   |v[i] - v[i-1]| > 3*std        -> warning
    - alarm_min / alarm_max: v < min_alarm / v > max_alarm -> critical
    - quality: quality != 192                -> warning, details="quality=<code>"
    - Sorted by timestamp; de-duplicate (a point can be both zscore and alarm — keep both types)
    """
```

### 2.2 `chart_generator.py` — server-side matplotlib (Agg backend)

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
from datetime import datetime

# dark theme constants matching the frontend
BG = "#111827"; PANEL = "#1f2937"; GRID = "#374151"
TICK = "#9ca3af"; LINE = "#60a5fa"; ANOMALY = "#ef4444"

def generate_timeseries_chart(
    timestamps: list[datetime], values: list[float | None],
    anomaly_timestamps: list[datetime], tag_name: str, unit: str,
    width_in: float = 10, height_in: float = 3.5,
) -> bytes:
    """Line chart, dark theme, red scatter dots at anomaly_timestamps. Returns PNG bytes."""

def generate_summary_bar_chart(tag_names: list[str], avg_values: list[float], unit: str) -> bytes:
    """Horizontal bar chart of per-tag averages. Returns PNG bytes."""
```

Each function builds a `Figure`, sets facecolors/spines/ticks to the dark constants, writes to `BytesIO(format="png", dpi=120)`, closes the figure (`plt.close(fig)` — critical for memory in the long-running process), returns bytes.

### 2.3 `excel_builder.py` — openpyxl, independent of `reports.py`

```python
def build_advanced_excel(
    archive, per_tag_data: list[dict], template, summary_chart_png: bytes
) -> bytes:
    """
    per_tag_data item: {
      "tag": Tag, "stats": TagStats, "anomalies": list[AnomalyEvent],
      "period_rows": list[dict],  # [{period, mean, min, max, count}]
      "chart_png": bytes
    }
    Sheets:
      1. "Ozet"   -> if show_summary_stats: stats table for all tags + embedded summary chart (XLImage)
      2. per tag  -> "<TagName>"[:31]: stats block, anomaly sub-table (if show_anomaly_table),
                     # openpyxl hard-limits sheet titles to 31 chars (old reports.py uses [:31])
                     embedded timeseries chart (if show_trend_charts), period table
      3. "Ham Veri" -> only if template.show_raw_data: raw readings
    Embedding:
      from openpyxl.drawing.image import Image as XLImage
      img = XLImage(BytesIO(chart_png)); img.width, img.height = 700, 245
      ws.add_image(img, "A<row>")
    Styling: header PatternFill(fgColor="1F2937"), Font(color="FFFFFF", bold=True),
             float number_format "#,##0.000".
    Return wb saved to BytesIO.
    """
```

### 2.4 `pdf_builder.py` + `app/templates/report.html.j2`

```python
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import base64, os

_env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")))

def build_pdf(archive, per_tag_data, template, facility_name: str, generated_at) -> bytes:
    for td in per_tag_data:
        td["chart_b64"] = base64.b64encode(td["chart_png"]).decode()
    html = _env.get_template("report.html.j2").render(
        archive=archive, template=template, per_tag_data=per_tag_data,
        facility_name=facility_name, generated_at=generated_at,
    )
    return HTML(string=html).write_pdf()
```

`report.html.j2` structure:
- `@page { margin: 2cm; @bottom-center { content: "Sayfa " counter(page) " / " counter(pages); } }`
- Header: facility name, template name, period `{{ archive.start }}–{{ archive.end }}`, generated-at
- `{% for td in per_tag_data %}` section (with `page-break-inside: avoid`): stats table + `<img src="data:image/png;base64,{{ td.chart_b64 }}">` (if `show_trend_charts`) + anomaly table (if `show_anomaly_table`)
- Summary section: top-10 anomalies across all tags + system health (avg availability %, total anomaly count)
- Professional print CSS: dark-on-white, subtle borders, sans-serif.

### 2.5 `report_generator.py` — orchestrator

```python
from datetime import datetime, timedelta, UTC
import gzip, json, uuid, os
from sqlalchemy import select
import pandas as pd

def resolve_time_range(template) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return {
        "last_1h":  (now - timedelta(hours=1), now),
        "last_24h": (now - timedelta(hours=24), now),
        "last_7d":  (now - timedelta(days=7), now),
        "last_30d": (now - timedelta(days=30), now),
        "custom":   (template.custom_start, template.custom_end),
    }[template.time_range_type]

async def generate_report_from_template(template, start, end, db, archive_id) -> "ReportArchive":
    """
    1. archive = await db.get(ReportArchive, archive_id)
       archive.status = "running"; archive.started_at = now; commit
    2. tag_ids = json.loads(template.tag_ids); load Tag rows
    3. For each tag:
         rows = (await db.execute(
             select(TagReading.timestamp, TagReading.value, TagReading.quality)
             .where(TagReading.tag_id == tag.id,
                    TagReading.timestamp >= start, TagReading.timestamp <= end)
             .order_by(TagReading.timestamp))).all()
         stats = compute_tag_stats(rows, tag.id, tag.name, tag.unit, levels)
         anomalies = detect_anomalies(rows, stats, threshold, tag.min_alarm, tag.max_alarm)
                     if template.anomaly_enabled else []
         chart = generate_timeseries_chart(...) if template.show_trend_charts else b""
         period_rows = _aggregate_periods(rows, template.interval)  # pandas resample
    4. summary_chart = generate_summary_bar_chart(names, avgs, unit)
    5. Build by format:
         excel -> build_advanced_excel(...) ; ext "xlsx"
         pdf   -> build_pdf(...)            ; ext "pdf"
         json  -> json.dumps(serialized)    ; ext "json"
       Write bytes to reports/<uuid>.<ext>; archive.file_path, file_size_bytes
    6. summary = {"tags": [{name, stats(asdict), anomaly_count}], "generated_at": ...}
       archive.result_json = gzip.compress(json.dumps(summary, default=str).encode())
    7. archive.status = "completed"; archive.completed_at = now; commit
    Exception path: archive.status = "failed"; archive.error_message = str(e); commit; re-raise-or-log
    """

def _aggregate_periods(rows, interval: str) -> list[dict]:
    freq = {"hourly": "h", "daily": "D", "weekly": "W"}[interval]
    df = pd.DataFrame([(t, v) for t, v, q in rows if v is not None and q == 192],
                      columns=["timestamp", "value"])
    if df.empty: return []
    df["timestamp"] = pd.to_datetime(df["timestamp"]); df.set_index("timestamp", inplace=True)
    g = df["value"].resample(freq).agg(["mean", "min", "max", "count"]).dropna()
    return [{"period": idx.isoformat(), "mean": round(r["mean"], 3),
             "min": round(r["min"], 3), "max": round(r["max"], 3), "count": int(r["count"])}
            for idx, r in g.iterrows()]
```

### 2.6 `scheduler.py` — APScheduler (AsyncIOScheduler + SQLAlchemyJobStore)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

_scheduler: AsyncIOScheduler | None = None
def get_scheduler(): return _scheduler

def _sync_db_url(async_url: str) -> str:
    return (async_url.replace("postgresql+asyncpg://", "postgresql://")
                     .replace("sqlite+aiosqlite:///", "sqlite:///"))

async def start_scheduler(db_url: str):
    global _scheduler
    _scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=_sync_db_url(db_url))},
        executors={"default": AsyncIOExecutor()},
    )
    _scheduler.start()
    await _sync_db_to_scheduler()   # re-register active ScheduledReport rows (idempotent)

async def register_job(scheduled) -> str:
    job_id = f"sr_{scheduled.id}"
    if scheduled.schedule_type == "cron":
        _scheduler.add_job(_run_scheduled_report, "cron", id=job_id, args=[scheduled.id],
                           hour=scheduled.cron_hour, minute=scheduled.cron_minute or 0,
                           day_of_week=scheduled.cron_day_of_week, day=scheduled.cron_day_of_month,
                           replace_existing=True)
    else:
        _scheduler.add_job(_run_scheduled_report, "interval", id=job_id, args=[scheduled.id],
                           hours=scheduled.interval_hours, replace_existing=True)
    return job_id

async def remove_job(job_id: str):
    if _scheduler and _scheduler.get_job(job_id): _scheduler.remove_job(job_id)

async def _run_scheduled_report(scheduled_report_id: int):
    """
    APScheduler job fn. Creates its OWN AsyncSessionLocal (no Depends in background).
    - load ScheduledReport + Template
    - sr.last_run_status="running"; sr.last_run_at=now; commit
    - create ReportArchive(status="pending", trigger="scheduled", scheduled_report_id=...)
    - start, end = resolve_time_range(template)
    - try: generate_report_from_template(...); sr.last_run_status="completed"
      except e: sr.last_run_status="failed"; sr.last_run_error=str(e)
    - sr.next_run_at = _scheduler.get_job(f"sr_{id}").next_run_time
    """
```

**Caveat (note in plan, validate at impl):** `SQLAlchemyJobStore` pickles the job's callable, so `_run_scheduled_report` must be a module-level function (it is). Cross-process restart works because the jobstore persists triggers; `_sync_db_to_scheduler()` reconciles DB truth with the store on boot.

---

## Part 3 — API Layer (`app/api/advanced_reports.py`)

New router, prefix `/api/advanced-reports`. Reuses `get_current_user` / role guards from `app/api/auth.py`. Schemas may live inline or in `app/schemas/advanced_reports.py`.

```
# --- Templates ---
GET    /advanced-reports/templates            -> list[TemplateResponse]
POST   /advanced-reports/templates            -> TemplateResponse        (admin|operator)
GET    /advanced-reports/templates/{id}       -> TemplateResponse
PUT    /advanced-reports/templates/{id}       -> TemplateResponse        (admin|operator)
DELETE /advanced-reports/templates/{id}       -> 204                     (admin)
POST   /advanced-reports/templates/{id}/run   -> ArchiveEntryResponse    (admin|operator)
   body: { start?: datetime, end?: datetime }  # falls back to template.time_range_type
   Creates ReportArchive(pending), dispatches generation as asyncio background task,
   returns the archive row immediately (status pending/running). Frontend polls archive.

# --- Scheduled ---
GET    /advanced-reports/scheduled            -> list[ScheduledResponse]
POST   /advanced-reports/scheduled            -> ScheduledResponse       (admin)  # + register_job
PUT    /advanced-reports/scheduled/{id}       -> ScheduledResponse       (admin)  # + re-register
DELETE /advanced-reports/scheduled/{id}       -> 204                     (admin)  # + remove_job
PATCH  /advanced-reports/scheduled/{id}/toggle-> ScheduledResponse       (admin)  # add/remove job

# --- Archive ---
GET    /advanced-reports/archive              -> PaginatedArchiveResponse
   params: page=1, page_size=50, template_id?, status?, date_from?, date_to?
GET    /advanced-reports/archive/{id}         -> ArchiveEntryResponse
GET    /advanced-reports/archive/{id}/download-> FileResponse (xlsx/pdf/json by output_format)
DELETE /advanced-reports/archive/{id}         -> 204 + unlink file       (admin)
```

Pydantic schemas:

```python
class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    tag_ids: list[int]
    time_range_type: str = "last_24h"
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    interval: str = "hourly"
    output_format: str = "excel"
    include_std_dev: bool = True
    include_percentiles: bool = True
    percentile_levels: list[int] = [10, 25, 50, 75, 90, 95]
    include_trend_line: bool = True
    anomaly_enabled: bool = True
    anomaly_zscore_threshold: float = 3.0
    show_summary_stats: bool = True
    show_trend_charts: bool = True
    show_anomaly_table: bool = True
    show_raw_data: bool = False

class TemplateResponse(TemplateCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
    # NOTE: tag_ids / percentile_levels stored as JSON text in DB; convert in a
    #       from_orm helper (json.loads) since response uses list types.

class ScheduledCreate(BaseModel):
    template_id: int
    name: str
    schedule_type: str          # cron|interval
    cron_hour: int | None = None
    cron_minute: int | None = 0
    cron_day_of_week: str | None = None
    cron_day_of_month: int | None = None
    interval_hours: int | None = None

class ScheduledResponse(ScheduledCreate):
    id: int
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_error: str | None
    next_run_at: datetime | None
    model_config = {"from_attributes": True}

class ArchiveEntryResponse(BaseModel):
    id: int
    template_id: int | None
    scheduled_report_id: int | None
    status: str
    trigger: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    tag_ids: list[int]
    start: datetime
    end: datetime
    interval: str
    output_format: str
    file_path: str | None
    file_size_bytes: int | None

class PaginatedArchiveResponse(BaseModel):
    items: list[ArchiveEntryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
```

---

## Part 4 — `app/main.py` Changes (current file: 93 lines)

```python
# line ~10, extend import:
from app.api import advanced_reports, auth, dashboard, explore, query, reports, tags
# after line 17, register new models for create_all:
from app.models import report_archive, report_template, scheduled_report  # noqa: F401
from app.services.scheduler import get_scheduler, start_scheduler

# inside lifespan() after DB tables ready (after line 41), BEFORE S7 connect:
    await start_scheduler(settings.DATABASE_URL)
    logger.info("APScheduler baslatildi")

# in teardown (after line 59 `yield`, before opcua stop):
    sched = get_scheduler()
    if sched:
        sched.shutdown(wait=False)

# after line 87 router includes:
app.include_router(advanced_reports.router, prefix="/api")
```

## Part 5 — `app/core/config.py` Additions

```python
FACILITY_NAME: str = "Su/Atıksu Tesisi"
REPORT_ARCHIVE_KEEP_DAYS: int = 365   # reserved for a future purge job
```

---

## Part 6 — Frontend

### 6.1 `src/api/client.ts` — append types + functions

Interfaces: `ReportTemplate`/`TemplateCreate`, `ScheduledReport`/`ScheduledCreate`, `ArchiveEntry`, `PaginatedArchive`.
Functions: `listTemplates`, `createTemplate`, `updateTemplate`, `deleteTemplate`, `runTemplate`, `listScheduled`, `createScheduled`, `updateScheduled`, `toggleScheduled`, `deleteScheduled`, `getArchive`, `downloadArchiveReport`. (Full signatures mirror the API in Part 3; blob `responseType: 'blob'` for download.)

### 6.2 `src/pages/AdvancedReports.tsx` — new page

Tab state: `useState<'templates' | 'scheduled' | 'archive'>('templates')`.

**Tab 1 — Şablonlar (Templates)**
- Table: Ad, Format, Interval, Tag count, Oluşturma, Actions (Çalıştır / Düzenle / Sil).
- "Yeni Şablon" opens `TemplateEditorModal`.
- "Şimdi Çalıştır" → `runTemplate(id)` mutation → toast → switch to Archive tab (which polls).

**`TemplateEditorModal`** — 4-step wizard (Geri / İleri):
1. *Tag Seçimi*: replicate the device-grouped toggle pattern from `Reports.tsx` (~30 lines, local state).
2. *Seçenekler*: time-range radios (Son 1s/24s/7g/30g/Özel → two `datetime-local` if Özel); interval (Saatlik/Günlük/Haftalık); format (Excel/PDF/JSON); stat checkboxes (Std Sapma, Persentiller, Trend Çizgisi).
3. *Anomali & Bölümler*: anomaly enable toggle; z-score slider (0.5–5.0, step 0.1); section toggles (Özet İstatistik, Trend Grafikleri, Anomali Tablosu, Ham Veri).
4. *Önizleme & Kaydet*: read-only summary + Ad + Açıklama inputs → submit mutation.

**Tab 2 — Zamanlanmış (Scheduled)**
- Table: Ad, Şablon, Program (human-readable), Aktif toggle, Son Çalışma, Durum badge, Sonraki Çalışma, Sil.
- `StatusBadge`: completed=green, running=blue `animate-spin`, failed=red, pending=gray.
- "Yeni Zamanlama" → `ScheduleCreateModal`: template dropdown, schedule type (Önceden Tanımlı: Günlük HH:MM / Haftalık gün+saat / Aylık ayın günü+saat, OR Her N Saatte: hours input), name.
- Active toggle → `toggleScheduled(id)` optimistic.

**Tab 3 — Arşiv (Archive)**
- Filter bar: template dropdown, status select (Hepsi/Tamamlandı/Başarısız/Çalışıyor/Beklemede), date-from/date-to.
- Paginated table (50/page): Tarih, Şablon, Tetikleyen (manual/scheduled), Dönem, Format, Durum badge, Boyut, İndir.
- `refetchInterval: hasRunningOrPending ? 5000 : false`.
- Pagination: Önceki / page numbers / Sonraki.

### 6.3 `src/components/Layout.tsx`
Add nav entry (keep existing `/reports`):
```ts
{ to: '/advanced-reports', label: 'Gelişmiş Raporlar',
  icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' }
```

### 6.4 `src/App.tsx`
```tsx
import AdvancedReports from './pages/AdvancedReports'
<Route path="advanced-reports" element={<AdvancedReports />} />
```

---

## File Structure Summary

```
backend/app/
  api/advanced_reports.py            ← NEW
  schemas/advanced_reports.py        ← NEW (optional; or inline in router)
  models/report_template.py          ← NEW
  models/scheduled_report.py         ← NEW
  models/report_archive.py           ← NEW
  services/__init__.py               ← NEW
  services/stats_engine.py           ← NEW
  services/chart_generator.py        ← NEW
  services/excel_builder.py          ← NEW
  services/pdf_builder.py            ← NEW
  services/report_generator.py       ← NEW
  services/scheduler.py              ← NEW
  templates/report.html.j2           ← NEW
  main.py                            ← MODIFY (imports, lifespan, router)
  core/config.py                     ← MODIFY (2 fields)
alembic/env.py                       ← MODIFY (3 imports)
alembic/versions/<rev>_advanced_reporting.py ← NEW

frontend/src/
  api/client.ts                      ← MODIFY (append)
  pages/AdvancedReports.tsx          ← NEW
  components/Layout.tsx              ← MODIFY (1 nav entry)
  App.tsx                            ← MODIFY (1 route)
```

---

## Implementation Order (TDD where it pays off)

1. **DB foundation**: 3 models → `alembic/env.py` imports → autogenerate migration → review → `just migrate`.
2. **Stats engine**: `stats_engine.py` (numpy only — no scipy) + unit tests with synthetic tuples (no DB) in `tests/test_stats_engine.py`. Highest test ROI — pure math.
3. **Builders**: `chart_generator.py` (eyeball a saved PNG) → `excel_builder.py` (open xlsx) → `report.html.j2` → `pdf_builder.py` (open PDF).
4. **Orchestrator**: `report_generator.py`; integration-test against dev SQLite with seeded readings.
5. **Scheduler**: `scheduler.py` + `main.py` lifespan wiring; verify `apscheduler_jobs` table appears and a job survives a restart.
6. **API**: `advanced_reports.py` router → register in `main.py` → smoke-test via `/docs`.
7. **Frontend**: `client.ts` → Archive tab (validates API first, least UI) → Templates tab + wizard → Scheduled tab → routing + sidebar.

---

## Reuse vs. Replace

| Existing | Action |
|---|---|
| `app/api/reports.py`, `/reports/generate`, `/reports/history` | **Untouched** — CLI depends on it |
| `ReportHistory` model | Keep — still written by old endpoint |
| `_fetch_aggregated()` (SQL-side agg) | **Do not reuse** — SQLite lacks `PERCENTILE_CONT`/`STDDEV`; new system pulls raw rows + numpy/pandas (no scipy) |
| `get_current_user` / role guards (`auth.py`) | Reuse in every new endpoint |
| `AsyncSessionLocal` (`database.py`) | Reuse in scheduler job (own session, no `Depends`) |
| Tag-toggle grouped UI (`Reports.tsx`) | Replicate ~30 lines in wizard Step 1 (tightly coupled to local state) |
| Modal pattern (`Tags.tsx`) | Reuse `fixed inset-0 bg-black/60 …` |
| Recharts dark config (`Trend.tsx`) | Style reference only — report charts are server-side matplotlib |
| `datetime.now(UTC)` convention (`s7_collector.py`) | Follow it in all new models/services |

---

## Key Design Decisions

- **Raw fetch over SQL aggregation:** percentiles, std dev, z-score, and gap analysis need the actual points. SQLite can't do `PERCENTILE_CONT`. 30d × 10 tags × 5s ≈ 5.2M rows; numpy/pandas handle that in-memory in ~1s. The poller writes every 5s, so windows stay bounded.
- **Separate `ReportArchive` (not extending `ReportHistory`):** new fields (status lifecycle, scheduled FK, gzip payload, trigger) are incompatible; clean split also drops the legacy 10-record eviction.
- **`SQLAlchemyJobStore` over a custom scheduler table:** ships with APScheduler, handles persistence/serialization/missed-fire. Only friction: needs a *sync* DB URL → `_sync_db_url()` helper.
- **Background generation + polling (not sync request):** PDF/Excel with charts over 5M rows can take seconds; `/run` returns a `pending` archive immediately and the Archive tab polls every 5s while running. Avoids HTTP timeouts and keeps the UI responsive.
- **gzip `result_json` in DB:** aggregated summary (~<50KB) compressed for quick preview/filtering without re-reading the file or recomputing.

---

## Verification

- `pytest` — existing 34 tests stay green; new `stats_engine` unit tests pass.
- `just run-backend` → `/docs`: create template → `POST /templates/{id}/run` → poll archive → download xlsx/pdf, open and inspect charts + anomaly tables.
- Create a `ScheduledReport` (interval 1h or a near-future cron) → confirm `last_run_at`/`last_run_status` populate after firing.
- Confirm `apscheduler_jobs` table exists in `scada_reporter.db`; restart backend → job still registered (`get_job` non-null).
- Frontend: wizard saves template → Scheduled tab adds schedule → Archive tab shows running→completed transition with live polling.
