# Excel Template Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-fill branded monthly Excel templates from collected SCADA data — map each data column to a PLC tag, write daily aggregates per day-row, preserve the template's exact format.

**Architecture:** New `app/services/template_fill/` module. A `tag_readings_1d` TimescaleDB continuous aggregate (with SQLite fallback) provides per-tag/day aggregates via a single `daily_values()` interface. An inspector auto-detects the template layout + proposes column→tag mapping; the user confirms it (stored in two new tables); a fill engine writes values into a clean template copy and returns xlsx bytes. A new React page drives upload → confirm → generate.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 async, openpyxl, Alembic, pytest-asyncio; React 19 + Vite + Tailwind v4 + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-06-16-excel-template-fill-design.md`

---

## Refinement vs spec (read first)

The spec proposed computing `last`/`first`/`delta` via `DISTINCT ON` on the raw `tag_readings` table. Raw retention is **7 days** (`core/config.py:RAW_RETENTION_DAYS`), so historical `last`/`delta` would be unrecoverable. **This plan instead stores `first` and `last` inside the `tag_readings_1d` continuous aggregate** alongside `avg/min/max/sum/count`. If a TimescaleDB version rejects `first()`/`last()` in a CAGG, the existing try/except in `init_continuous_aggregates` logs and skips — and the SQLite/dev path computes every agg by bucketing readings in Python. Net effect: `daily_values()` is the single source of truth and `delta = last − first` works for any retained day.

## File Structure

**Backend — create:**
- `app/services/template_fill/__init__.py` — package marker
- `app/services/template_fill/daily_rollup.py` — `daily_values()` interface (SQLite + Timescale paths)
- `app/services/template_fill/template_inspector.py` — layout auto-detect + mapping proposal
- `app/services/template_fill/fill_engine.py` — fill clean template → xlsx bytes
- `app/models/excel_template.py` — `ExcelTemplate` + `ExcelTemplateColumn`
- `app/api/excel_templates.py` — REST router
- `alembic/versions/f1a2b3c4d5e6_excel_templates.py` — migration
- `tests/test_daily_rollup.py`, `tests/test_template_inspector.py`, `tests/test_fill_engine.py`, `tests/test_excel_templates_api.py`

**Backend — modify:**
- `app/core/timescaledb.py` — add `tag_readings_1d` CAGG (no retention; with sum/first/last)
- `app/main.py` — import new model module; register router
- `app/core/config.py` — add `REPORT_TZ_OFFSET_HOURS` setting

**Frontend — create:**
- `frontend/src/pages/ExcelTemplates.tsx` — the page (list / upload+confirm / generate)
- `frontend/src/pages/ExcelTemplates.test.tsx` — vitest on mapping-grid state

**Frontend — modify:**
- `frontend/src/App.tsx` — route
- `frontend/src/components/Layout.tsx` — sidebar entry
- regenerate `frontend/src/api/` via `just gen-client`

---

## Task 1: `daily_values()` aggregation interface

**Files:**
- Create: `app/services/template_fill/__init__.py`
- Create: `app/services/template_fill/daily_rollup.py`
- Create: `tests/test_daily_rollup.py`
- Modify: `app/core/config.py`

- [ ] **Step 1: Add the timezone-offset setting**

In `app/core/config.py`, inside the `Settings` class (next to other report settings), add:

```python
    # Rapor gün sınırı için yerel saat ofseti (UTC+3 İstanbul). Günlük
    # toplamalar bu ofsetle kaydırılmış tarihe göre gruplanır.
    REPORT_TZ_OFFSET_HOURS: int = 3
```

- [ ] **Step 2: Create the package marker**

Create `app/services/template_fill/__init__.py`:

```python
```

(empty file)

- [ ] **Step 3: Write the failing test**

Create `tests/test_daily_rollup.py`:

```python
from datetime import datetime

import pytest
import pytest_asyncio

from app.models.tag import Tag, TagReading
from app.services.template_fill.daily_rollup import daily_values


@pytest_asyncio.fixture
async def tag_with_readings(db_session):
    tag = Tag(node_id="n1", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.flush()
    # Day 1: values 10, 20, 30 (sum 60, avg 20, min 10, max 30, last 30, delta 20)
    # Day 2: single value 5 (last 5, delta None)
    rows = [
        TagReading(tag_id=tag.id, value=10.0, timestamp=datetime(2026, 5, 1, 1, 0)),
        TagReading(tag_id=tag.id, value=20.0, timestamp=datetime(2026, 5, 1, 8, 0)),
        TagReading(tag_id=tag.id, value=30.0, timestamp=datetime(2026, 5, 1, 20, 0)),
        TagReading(tag_id=tag.id, value=5.0, timestamp=datetime(2026, 5, 2, 12, 0)),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return tag


@pytest.mark.asyncio
async def test_sum_avg_min_max(db_session, tag_with_readings):
    tag = tag_with_readings
    assert await daily_values(db_session, tag.id, 2026, 5, "sum") == {1: 60.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "avg") == {1: 20.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "min") == {1: 10.0, 2: 5.0}
    assert await daily_values(db_session, tag.id, 2026, 5, "max") == {1: 30.0, 2: 5.0}


@pytest.mark.asyncio
async def test_last_and_delta(db_session, tag_with_readings):
    tag = tag_with_readings
    assert await daily_values(db_session, tag.id, 2026, 5, "last") == {1: 30.0, 2: 5.0}
    # delta = last - first; day 2 has a single reading -> None (omitted)
    assert await daily_values(db_session, tag.id, 2026, 5, "delta") == {1: 20.0}


@pytest.mark.asyncio
async def test_tz_offset_shifts_day(db_session):
    # 2026-05-01 23:00 UTC + 3h offset -> 2026-05-02 local
    tag = Tag(node_id="n2", name="X", unit="")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(TagReading(tag_id=tag.id, value=7.0, timestamp=datetime(2026, 5, 1, 23, 0)))
    await db_session.commit()
    result = await daily_values(db_session, tag.id, 2026, 5, "last", tz_offset_hours=3)
    assert result == {2: 7.0}


@pytest.mark.asyncio
async def test_unknown_agg_raises(db_session, tag_with_readings):
    with pytest.raises(ValueError):
        await daily_values(db_session, tag_with_readings.id, 2026, 5, "median")
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_daily_rollup.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.template_fill.daily_rollup`

- [ ] **Step 5: Implement `daily_rollup.py`**

Create `app/services/template_fill/daily_rollup.py`:

```python
"""Günlük tag toplama arayüzü.

Tek giriş noktası: daily_values(). PostgreSQL/Timescale'de tag_readings_1d
sürekli toplama view'ından okur; SQLite/dev'de ham tag_readings'i Python'da
gün bazında gruplar. delta = günün son okuması - ilk okuması.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import TagReading

AGGS = {"sum", "avg", "min", "max", "last", "delta"}


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _reduce(values: list[float], agg: str) -> float | None:
    """values: günün okumaları, zaman sırasına göre. agg uygula."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if agg == "sum":
        return sum(vals)
    if agg == "avg":
        return sum(vals) / len(vals)
    if agg == "min":
        return min(vals)
    if agg == "max":
        return max(vals)
    if agg == "last":
        return vals[-1]
    if agg == "delta":
        return vals[-1] - vals[0] if len(vals) >= 2 else None
    raise ValueError(f"Bilinmeyen agg: {agg}")


async def _daily_sqlite(
    db: AsyncSession, tag_id: int, year: int, month: int, agg: str, tz_offset_hours: int
) -> dict[int, float]:
    start, end = _month_bounds(year, month)
    # Ofset penceresi: yerel gün sınırı UTC'de kayar
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    result = await db.execute(
        select(TagReading.timestamp, TagReading.value)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= q_start,
            TagReading.timestamp < q_end,
        )
        .order_by(TagReading.timestamp.asc())
    )
    buckets: dict[int, list[float]] = defaultdict(list)
    for ts, value in result.all():
        local = ts + timedelta(hours=tz_offset_hours)
        if local.year == year and local.month == month:
            buckets[local.day].append(value)
    out: dict[int, float] = {}
    for day, vals in buckets.items():
        reduced = _reduce(vals, agg)
        if reduced is not None:
            out[day] = reduced
    return out


_CAGG_COL = {"sum": "sum", "avg": "avg", "min": "min", "max": "max", "last": "last_v"}


async def _daily_timescale(
    db: AsyncSession, tag_id: int, year: int, month: int, agg: str, tz_offset_hours: int
) -> dict[int, float]:
    start, end = _month_bounds(year, month)
    shift = f"INTERVAL '{tz_offset_hours} hours'"
    # bucket UTC günü; yerel güne kaydır
    if agg == "delta":
        sel = "last_v - first_v AS val, count(*) over () "  # placeholder; computed below
        rows = await db.execute(
            text(
                "SELECT EXTRACT(DAY FROM (bucket + " + shift + "))::int AS d, "
                "(last_v - first_v) AS val, n "
                "FROM tag_readings_1d "
                "WHERE tag_id = :tid AND (bucket + " + shift + ") >= :s "
                "AND (bucket + " + shift + ") < :e"
            ),
            {"tid": tag_id, "s": start, "e": end},
        )
        return {int(d): float(v) for d, v, n in rows.all() if v is not None and n >= 2}
    col = _CAGG_COL[agg]
    rows = await db.execute(
        text(
            "SELECT EXTRACT(DAY FROM (bucket + " + shift + "))::int AS d, "
            f"{col} AS val FROM tag_readings_1d "
            "WHERE tag_id = :tid AND (bucket + " + shift + ") >= :s "
            "AND (bucket + " + shift + ") < :e"
        ),
        {"tid": tag_id, "s": start, "e": end},
    )
    return {int(d): float(v) for d, v in rows.all() if v is not None}


async def daily_values(
    db: AsyncSession,
    tag_id: int,
    year: int,
    month: int,
    agg: str,
    tz_offset_hours: int = 0,
) -> dict[int, float]:
    """{gün_no: değer} döndür. Verisi olmayan gün anahtarsız (sıfır uydurma yok)."""
    if agg not in AGGS:
        raise ValueError(f"Bilinmeyen agg: {agg}")
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "postgresql":
        return await _daily_timescale(db, tag_id, year, month, agg, tz_offset_hours)
    return await _daily_sqlite(db, tag_id, year, month, agg, tz_offset_hours)
```

Note: the `sel` line in `_daily_timescale` for the delta branch is unused — remove it; the actual query is the `text(...)` below it. (Engineer: delete the `sel = ...` placeholder line.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_daily_rollup.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/__init__.py \
        scada-reporter/backend/app/services/template_fill/daily_rollup.py \
        scada-reporter/backend/tests/test_daily_rollup.py \
        scada-reporter/backend/app/core/config.py
git commit -m "feat(reports): daily_values aggregation interface (sum/avg/min/max/last/delta)"
```

---

## Task 2: `tag_readings_1d` continuous aggregate

**Files:**
- Modify: `app/core/timescaledb.py`

This is Timescale-only (CI/SQLite skip it). No unit test — verified by the existing try/except logging + manual prod check.

- [ ] **Step 1: Add the daily CAGG builder**

In `app/core/timescaledb.py`, after `init_continuous_aggregates`, add:

```python
async def init_daily_rollup(conn: AsyncConnection) -> None:
    """Uzun saklamalı günlük toplama (rapor şablonları için).

    avg/min/max/sum/first/last/count saklar. Retention YOK — yıllarca tutulur.
    first/last bir Timescale sürümünde reddedilirse hata loglanıp atlanır;
    o durumda last/delta yalnız SQLite/dev'de hesaplanabilir.
    """
    try:
        await conn.execute(
            text(
                "CREATE MATERIALIZED VIEW IF NOT EXISTS tag_readings_1d "
                "WITH (timescaledb.continuous) AS "
                "SELECT tag_id, time_bucket(INTERVAL '1 day', timestamp) AS bucket, "
                "avg(value) AS avg, min(value) AS min, max(value) AS max, "
                "sum(value) AS sum, count(*) AS n, "
                "first(value, timestamp) AS first_v, last(value, timestamp) AS last_v "
                "FROM tag_readings GROUP BY tag_id, bucket WITH NO DATA"
            )
        )
        await conn.execute(
            text(
                "SELECT add_continuous_aggregate_policy('tag_readings_1d', "
                "start_offset => INTERVAL '7 days', "
                "end_offset => INTERVAL '1 hour', "
                "schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
            )
        )
        logger.info("Daily rollup ready: tag_readings_1d (no retention)")
    except Exception as e:
        logger.info("Daily rollup skipped/exists: %s", e)
```

- [ ] **Step 2: Call it from the CAGG init in `main.py`**

In `app/main.py`, update the import on line 30:

```python
from app.core.timescaledb import (
    init_continuous_aggregates,
    init_daily_rollup,
    init_timescaledb,
)
```

And in `lifespan`, in the AUTOCOMMIT block (currently lines 69-71), add the call:

```python
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await init_continuous_aggregates(conn)
        await init_daily_rollup(conn)
```

- [ ] **Step 3: Verify the app still boots (SQLite dev — CAGG silently skipped)**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -c "import app.main; print('ok')"`
Expected: prints `ok` with no import error.

- [ ] **Step 4: Commit**

```bash
git add scada-reporter/backend/app/core/timescaledb.py scada-reporter/backend/app/main.py
git commit -m "feat(reports): tag_readings_1d daily continuous aggregate (long retention)"
```

---

## Task 3: `ExcelTemplate` + `ExcelTemplateColumn` models & migration

**Files:**
- Create: `app/models/excel_template.py`
- Create: `alembic/versions/f1a2b3c4d5e6_excel_templates.py`
- Modify: `app/main.py` (import for `create_all`)
- Create: `tests/test_excel_template_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_template_model.py`:

```python
import pytest

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn


@pytest.mark.asyncio
async def test_template_with_columns_cascade(db_session):
    tpl = ExcelTemplate(
        name="Balta Aylık",
        file_blob=b"PK\x03\x04fake",
        sheet_name="OCAK 2026",
        header_row=2,
        date_col="D",
        data_start_row=3,
        date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(col_letter="E", tag_id=None, agg="sum", source_code="410BF103"),
        ExcelTemplateColumn(col_letter="F", tag_id=None, agg="delta", source_code="460BF105"),
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    assert tpl.id is not None
    assert len(tpl.columns) == 2
    assert tpl.columns[0].enabled is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_template_model.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.excel_template`

- [ ] **Step 3: Implement the models**

Create `app/models/excel_template.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExcelTemplate(Base):
    __tablename__ = "excel_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    file_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    date_col: Mapped[str] = mapped_column(String(4), nullable=False)
    data_start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    date_mode: Mapped[str] = mapped_column(String(8), default="write")  # write|match
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    columns: Mapped[list["ExcelTemplateColumn"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ExcelTemplateColumn.id",
    )


class ExcelTemplateColumn(Base):
    __tablename__ = "excel_template_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("excel_templates.id", ondelete="CASCADE"), nullable=False
    )
    col_letter: Mapped[str] = mapped_column(String(4), nullable=False)
    tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )
    agg: Mapped[str] = mapped_column(String(8), default="avg")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    template: Mapped["ExcelTemplate"] = relationship(back_populates="columns")
```

- [ ] **Step 4: Register the model for `create_all`**

In `app/main.py`, extend the noqa model import block (line 32) so tables auto-create in dev/test:

```python
from app.models import excel_template as _excel_template  # noqa: F401
```

(Add this line directly below the existing `from app.models import report_archive, report_template, scheduled_report  # noqa: F401`.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_template_model.py -v`
Expected: PASS

- [ ] **Step 6: Write the Alembic migration (for prod Postgres)**

Create `alembic/versions/f1a2b3c4d5e6_excel_templates.py`:

```python
"""excel templates + columns

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-16 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "excel_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_blob", sa.LargeBinary(), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("date_col", sa.String(length=4), nullable=False),
        sa.Column("data_start_row", sa.Integer(), nullable=False),
        sa.Column("date_mode", sa.String(length=8), nullable=False, server_default="write"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "excel_template_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("col_letter", sa.String(length=4), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("agg", sa.String(length=8), nullable=False, server_default="avg"),
        sa.Column("source_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["template_id"], ["excel_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_excel_template_columns_template_id", "excel_template_columns", ["template_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_excel_template_columns_template_id", table_name="excel_template_columns"
    )
    op.drop_table("excel_template_columns")
    op.drop_table("excel_templates")
```

- [ ] **Step 7: Verify migration chain is valid**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m alembic heads`
Expected: single head `f1a2b3c4d5e6 (head)` — no multiple heads / branch errors.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/backend/app/models/excel_template.py \
        scada-reporter/backend/tests/test_excel_template_model.py \
        scada-reporter/backend/alembic/versions/f1a2b3c4d5e6_excel_templates.py \
        scada-reporter/backend/app/main.py
git commit -m "feat(reports): ExcelTemplate + ExcelTemplateColumn models and migration"
```

---

## Task 4: `template_inspector` — auto-detect + mapping proposal

**Files:**
- Create: `app/services/template_fill/template_inspector.py`
- Create: `tests/test_template_inspector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_template_inspector.py`:

```python
from io import BytesIO

import pytest
import pytest_asyncio
from openpyxl import Workbook

from app.models.tag import Tag
from app.services.template_fill.template_inspector import inspect_template


def _make_template_bytes() -> bytes:
    """row1 başlık metni, row2 sensör kodları, row3+ tarih + boş grid."""
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK 2026"
    ws["D1"] = "TARİH"
    ws["E1"] = "TESİSE ALINAN DEBİ m3/gün"
    ws["F1"] = "ELEKTRİK TÜKETİMİ"
    ws["B1"] = "HAVA DURUMU"
    ws["D2"] = "SENSÖR KODLARI"
    ws["E2"] = "410BF103"
    ws["F2"] = "460BF105"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def seeded_tags(db_session):
    db_session.add_all([
        Tag(node_id="a", name="410BF103", unit="m3"),
        Tag(node_id="b", name="460BF105", unit="kWh"),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_detects_layout_and_mapping(db_session, seeded_tags):
    proposal = await inspect_template(db_session, _make_template_bytes())
    assert proposal["sheet_name"] == "OCAK 2026"
    assert proposal["header_row"] == 2
    assert proposal["date_col"] == "D"
    cols = {c["col_letter"]: c for c in proposal["columns"]}
    # E -> matched tag, agg guessed 'sum' from m3/gün label
    assert cols["E"]["source_code"] == "410BF103"
    assert cols["E"]["tag_id"] is not None
    assert cols["E"]["agg"] == "sum"
    # F -> matched, agg guessed 'delta' from TÜKETİM
    assert cols["F"]["agg"] == "delta"
    assert cols["F"]["tag_id"] is not None


@pytest.mark.asyncio
async def test_unmatched_code_is_unmapped(db_session):
    # no tags seeded -> codes present but no DB match
    proposal = await inspect_template(db_session, _make_template_bytes())
    cols = {c["col_letter"]: c for c in proposal["columns"]}
    assert cols["E"]["tag_id"] is None
    assert cols["E"]["source_code"] == "410BF103"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_template_inspector.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the inspector**

Create `app/services/template_fill/template_inspector.py`:

```python
"""Excel şablonu otomatik analiz: sayfa, başlık satırı, tarih sütunu, grid
başlangıcı tespit eder ve sensör kodlarından tag eşlemesi önerir."""

import re
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag

CODE_RE = re.compile(r"^\d{3}[A-Z]{2}\d{3}$")
_SCAN_ROWS = 6


def _norm(s: object) -> str:
    return str(s or "").strip().upper().replace("İ", "I").replace("Ş", "S")


def _guess_agg(label: str) -> str:
    u = _norm(label)
    if "M3/GUN" in u or "DEBI" in u:
        return "sum"
    if "TUKETIM" in u or "SAYAC" in u:
        return "delta"
    if "%" in label or "ORAN" in u:
        return "avg"
    if "SEVIYE" in u:
        return "last"
    return "avg"


def _find_code_row(ws) -> int:
    best_row, best_hits = 1, -1
    for r in range(1, min(ws.max_row, _SCAN_ROWS) + 1):
        hits = sum(
            1
            for c in ws[r]
            if isinstance(c.value, str) and CODE_RE.match(c.value.strip())
        )
        if hits > best_hits:
            best_row, best_hits = r, hits
    return best_row


def _find_date_col(ws, scan_rows: int) -> str:
    for r in range(1, scan_rows + 1):
        for c in ws[r]:
            if _norm(c.value) == "TARIH":
                return get_column_letter(c.column)
    return "A"


def _label_for(ws, col_idx: int, code_row: int) -> str:
    """Kod satırının üstündeki ilk dolu hücreyi etiket olarak al."""
    for r in range(code_row - 1, 0, -1):
        v = ws.cell(row=r, column=col_idx).value
        if v not in (None, ""):
            return str(v)
    return ""


async def inspect_template(db: AsyncSession, file_bytes: bytes) -> dict:
    wb = load_workbook(BytesIO(file_bytes), data_only=False)
    ws = wb.worksheets[0]
    code_row = _find_code_row(ws)
    date_col = _find_date_col(ws, min(ws.max_row, _SCAN_ROWS))

    codes: dict[int, str] = {}
    for c in ws[code_row]:
        if isinstance(c.value, str) and CODE_RE.match(c.value.strip()):
            codes[c.column] = c.value.strip()

    # tag adı -> id eşlemesi
    name_to_id: dict[str, int] = {}
    if codes:
        result = await db.execute(select(Tag.id, Tag.name).where(Tag.name.in_(codes.values())))
        name_to_id = {name: tid for tid, name in result.all()}

    columns = []
    for col_idx, code in sorted(codes.items()):
        label = _label_for(ws, col_idx, code_row)
        columns.append(
            {
                "col_letter": get_column_letter(col_idx),
                "source_code": code,
                "tag_id": name_to_id.get(code),
                "agg": _guess_agg(label),
                "label": label,
                "enabled": code in name_to_id,
            }
        )

    return {
        "sheet_name": ws.title,
        "header_row": code_row,
        "date_col": date_col,
        "data_start_row": code_row + 1,
        "date_mode": "write",
        "columns": columns,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_template_inspector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/template_inspector.py \
        scada-reporter/backend/tests/test_template_inspector.py
git commit -m "feat(reports): template_inspector auto-detect + tag mapping proposal"
```

---

## Task 5: `fill_engine` — write daily values into a template copy

**Files:**
- Create: `app/services/template_fill/fill_engine.py`
- Create: `tests/test_fill_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fill_engine.py`:

```python
from datetime import datetime
from io import BytesIO

import pytest
import pytest_asyncio
from openpyxl import Workbook, load_workbook

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.models.tag import Tag, TagReading
from app.services.template_fill.fill_engine import fill_template


def _template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK 2026"
    ws["D2"] = "SENSÖR KODLARI"
    ws["E2"] = "410BF103"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def saved_template(db_session):
    tag = Tag(node_id="a", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.flush()
    db_session.add_all([
        TagReading(tag_id=tag.id, value=10.0, timestamp=datetime(2026, 1, 1, 6, 0)),
        TagReading(tag_id=tag.id, value=30.0, timestamp=datetime(2026, 1, 1, 18, 0)),
        TagReading(tag_id=tag.id, value=50.0, timestamp=datetime(2026, 1, 3, 9, 0)),
    ])
    tpl = ExcelTemplate(
        name="T", file_blob=_template_bytes(), sheet_name="OCAK 2026",
        header_row=2, date_col="D", data_start_row=3, date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(col_letter="E", tag_id=tag.id, agg="sum", source_code="410BF103"),
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    return tpl


@pytest.mark.asyncio
async def test_fill_writes_daily_sums_and_dates(db_session, saved_template):
    out = await fill_template(db_session, saved_template.id, 2026, 1)
    ws = load_workbook(BytesIO(out)).active
    # day1 row = data_start_row(3) + 0 = 3 ; day3 row = 5
    assert ws["E3"].value == 40.0  # 10 + 30
    assert ws["E5"].value == 50.0
    assert ws["E4"].value is None  # day 2 no data -> blank, not 0
    # date column written (write mode)
    assert ws["D3"].value.day == 1
    assert ws["D5"].value.day == 3


@pytest.mark.asyncio
async def test_disabled_and_null_columns_skipped(db_session, saved_template):
    saved_template.columns[0].enabled = False
    await db_session.commit()
    out = await fill_template(db_session, saved_template.id, 2026, 1)
    ws = load_workbook(BytesIO(out)).active
    assert ws["E3"].value is None


@pytest.mark.asyncio
async def test_missing_template_raises(db_session):
    with pytest.raises(ValueError):
        await fill_template(db_session, 9999, 2026, 1)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_fill_engine.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the fill engine**

Create `app/services/template_fill/fill_engine.py`:

```python
"""Şablon kopyasına günlük değerleri yazıp xlsx bytes döndürür.

Temiz şablon (file_blob) yüklenir, seçilen ay için her eşlenmiş+aktif sütuna
günlük toplama yazılır. Verisi olmayan gün boş bırakılır (0 uydurma yok).
Hücre stili/format korunur — yalnız değer yazılır.
"""

import calendar
from datetime import datetime
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.excel_template import ExcelTemplate
from app.services.template_fill.daily_rollup import daily_values


async def fill_template(db: AsyncSession, template_id: int, year: int, month: int) -> bytes:
    result = await db.execute(
        select(ExcelTemplate)
        .where(ExcelTemplate.id == template_id)
        .options(selectinload(ExcelTemplate.columns))
    )
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise ValueError(f"Şablon bulunamadı: {template_id}")

    wb = load_workbook(BytesIO(tpl.file_blob), data_only=False)
    ws = wb[tpl.sheet_name] if tpl.sheet_name in wb.sheetnames else wb.worksheets[0]
    offset = settings.REPORT_TZ_OFFSET_HOURS
    ndays = calendar.monthrange(year, month)[1]

    # write modunda gün -> satır eşlemesi; match modunda mevcut tarih hücreleri
    day_to_row: dict[int, int] = {}
    if tpl.date_mode == "match":
        for r in range(tpl.data_start_row, ws.max_row + 1):
            v = ws[f"{tpl.date_col}{r}"].value
            if isinstance(v, datetime):
                day_to_row[v.day] = r
    else:
        for day in range(1, ndays + 1):
            day_to_row[day] = tpl.data_start_row + (day - 1)

    # write modunda tarihleri yaz
    if tpl.date_mode == "write":
        for day in range(1, ndays + 1):
            ws[f"{tpl.date_col}{day_to_row[day]}"] = datetime(year, month, day)

    for col in tpl.columns:
        if not col.enabled or col.tag_id is None:
            continue
        vals = await daily_values(db, col.tag_id, year, month, col.agg, tz_offset_hours=offset)
        for day, value in vals.items():
            row = day_to_row.get(day)
            if row is not None:
                ws[f"{col.col_letter}{row}"] = value

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_fill_engine.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/fill_engine.py \
        scada-reporter/backend/tests/test_fill_engine.py
git commit -m "feat(reports): fill_engine writes daily values into template copy"
```

---

## Task 6: REST API — `excel_templates` router

**Files:**
- Create: `app/api/excel_templates.py`
- Create: `tests/test_excel_templates_api.py`
- Modify: `app/main.py` (register router)

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_templates_api.py`:

```python
from io import BytesIO

import pytest
import pytest_asyncio
from openpyxl import Workbook

from app.api.auth import get_current_user
from app.main import app
from app.models.tag import Tag


def _template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK 2026"
    ws["D2"] = "SENSÖR KODLARI"
    ws["E2"] = "410BF103"
    ws["E1"] = "DEBİ m3/gün"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "admin"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seeded_tag(db_session):
    tag = Tag(node_id="a", name="410BF103", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    return tag


@pytest.mark.asyncio
async def test_inspect_returns_proposal(client, seeded_tag):
    resp = await client.post(
        "/api/excel-templates/inspect",
        files={"file": ("t.xlsx", _template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sheet_name"] == "OCAK 2026"
    assert data["columns"][0]["source_code"] == "410BF103"


@pytest.mark.asyncio
async def test_save_and_generate_roundtrip(client, seeded_tag):
    import base64
    payload = {
        "name": "Balta",
        "description": "",
        "file_b64": base64.b64encode(_template_bytes()).decode(),
        "sheet_name": "OCAK 2026",
        "header_row": 2,
        "date_col": "D",
        "data_start_row": 3,
        "date_mode": "write",
        "columns": [
            {"col_letter": "E", "tag_id": seeded_tag.id, "agg": "sum",
             "source_code": "410BF103", "enabled": True}
        ],
    }
    save = await client.post("/api/excel-templates", json=payload)
    assert save.status_code == 201, save.text
    tpl_id = save.json()["id"]

    listed = await client.get("/api/excel-templates")
    assert any(t["id"] == tpl_id for t in listed.json())

    gen = await client.post(f"/api/excel-templates/{tpl_id}/generate?year=2026&month=1")
    assert gen.status_code == 200
    assert gen.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert gen.content[:2] == b"PK"  # valid xlsx zip
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_templates_api.py -v`
Expected: FAIL — `ModuleNotFoundError: app.api.excel_templates`

- [ ] **Step 3: Implement the router**

Create `app/api/excel_templates.py`:

```python
import base64
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.services.template_fill.fill_engine import fill_template
from app.services.template_fill.template_inspector import inspect_template

router = APIRouter(prefix="/excel-templates", tags=["excel-templates"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ColumnIn(BaseModel):
    col_letter: str
    tag_id: int | None = None
    agg: str = "avg"
    source_code: str = ""
    enabled: bool = True


class TemplateIn(BaseModel):
    name: str
    description: str = ""
    file_b64: str
    sheet_name: str
    header_row: int
    date_col: str
    data_start_row: int
    date_mode: str = "write"
    columns: list[ColumnIn]


class ColumnOut(ColumnIn):
    id: int


class TemplateOut(BaseModel):
    id: int
    name: str
    description: str
    sheet_name: str
    header_row: int
    date_col: str
    data_start_row: int
    date_mode: str
    columns: list[ColumnOut]


def _to_out(tpl: ExcelTemplate) -> TemplateOut:
    return TemplateOut(
        id=tpl.id,
        name=tpl.name,
        description=tpl.description,
        sheet_name=tpl.sheet_name,
        header_row=tpl.header_row,
        date_col=tpl.date_col,
        data_start_row=tpl.data_start_row,
        date_mode=tpl.date_mode,
        columns=[
            ColumnOut(
                id=c.id, col_letter=c.col_letter, tag_id=c.tag_id, agg=c.agg,
                source_code=c.source_code, enabled=c.enabled,
            )
            for c in tpl.columns
        ],
    )


@router.post("/inspect")
async def inspect(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await file.read()
    try:
        return await inspect_template(db, data)
    except Exception as e:  # bozuk xlsx
        raise HTTPException(status_code=400, detail=f"Şablon okunamadı: {e}") from e


@router.post("", status_code=201, response_model=TemplateOut)
async def create_template(
    payload: TemplateIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        blob = base64.b64decode(payload.file_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail="file_b64 geçersiz") from e
    tpl = ExcelTemplate(
        name=payload.name,
        description=payload.description,
        file_blob=blob,
        sheet_name=payload.sheet_name,
        header_row=payload.header_row,
        date_col=payload.date_col,
        data_start_row=payload.data_start_row,
        date_mode=payload.date_mode,
        created_by=user.get("id") if isinstance(user, dict) else None,
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter=c.col_letter, tag_id=c.tag_id, agg=c.agg,
            source_code=c.source_code, enabled=c.enabled,
        )
        for c in payload.columns
    ]
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl, attribute_names=["columns"])
    return _to_out(tpl)


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    result = await db.execute(
        select(ExcelTemplate).options(selectinload(ExcelTemplate.columns))
    )
    return [_to_out(t) for t in result.scalars().all()]


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    tpl = await db.get(ExcelTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    await db.delete(tpl)
    await db.commit()


@router.post("/{template_id}/generate")
async def generate(
    template_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        data = await fill_template(db, template_id, year, month)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    fname = f"rapor_{year}_{month:02d}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
```

- [ ] **Step 4: Register the router in `main.py`**

In `app/main.py`, add `excel_templates` to the `from app.api import (...)` block (keep alphabetical-ish, after `explore`):

```python
from app.api import (
    advanced_reports,
    annotations,
    auth,
    dashboard,
    excel_templates,
    explore,
    groups,
    plc,
    query,
    realtime,
    reports,
    tags,
)
```

And add the include line next to the others (after `advanced_reports`):

```python
app.include_router(excel_templates.router, prefix="/api")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_templates_api.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full backend suite + lint**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check app tests`
Expected: all pass, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/api/excel_templates.py \
        scada-reporter/backend/tests/test_excel_templates_api.py \
        scada-reporter/backend/app/main.py
git commit -m "feat(reports): excel-templates REST API (inspect/save/list/generate/delete)"
```

---

## Task 7: Regenerate TS client + frontend page

**Files:**
- Regenerate: `frontend/src/api/`
- Create: `frontend/src/pages/ExcelTemplates.tsx`
- Create: `frontend/src/pages/ExcelTemplates.test.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Regenerate the OpenAPI client (backend must be running)**

Run in one terminal: `just run-backend`
Run in another: `just gen-client`
Expected: `frontend/src/api/` updated; `ExcelTemplate`-related types + service functions present. Stop the backend after.

- [ ] **Step 2: Write the failing vitest for mapping-grid state**

Create `frontend/src/pages/ExcelTemplates.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { applyAggChange, toSavePayload, type MappingRow } from "./ExcelTemplates";

const rows: MappingRow[] = [
  { col_letter: "E", source_code: "410BF103", label: "DEBİ m3/gün", tag_id: 1, agg: "sum", enabled: true },
  { col_letter: "B", source_code: "", label: "HAVA DURUMU", tag_id: null, agg: "avg", enabled: false },
];

describe("mapping grid state", () => {
  it("updates agg for one column only", () => {
    const next = applyAggChange(rows, "E", "delta");
    expect(next.find((r) => r.col_letter === "E")?.agg).toBe("delta");
    expect(next.find((r) => r.col_letter === "B")?.agg).toBe("avg");
  });

  it("save payload drops disabled/unmapped rows", () => {
    const payload = toSavePayload(
      { name: "T", description: "", file_b64: "AA==", sheet_name: "S", header_row: 2, date_col: "D", data_start_row: 3, date_mode: "write" },
      rows,
    );
    expect(payload.columns).toHaveLength(1);
    expect(payload.columns[0].col_letter).toBe("E");
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/ExcelTemplates.test.tsx`
Expected: FAIL — cannot import from `./ExcelTemplates` (not created yet).

- [ ] **Step 4: Implement the page with exported pure helpers**

Create `frontend/src/pages/ExcelTemplates.tsx`. Export the two pure helpers (`applyAggChange`, `toSavePayload`) and types so the test imports them; the component uses TanStack Query for I/O. Use the generated client functions from Step 1 (names may differ — match what `just gen-client` produced; the calls below are the contract).

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export type Agg = "sum" | "avg" | "min" | "max" | "last" | "delta";

export interface MappingRow {
  col_letter: string;
  source_code: string;
  label: string;
  tag_id: number | null;
  agg: Agg;
  enabled: boolean;
}

export interface TemplateMeta {
  name: string;
  description: string;
  file_b64: string;
  sheet_name: string;
  header_row: number;
  date_col: string;
  data_start_row: number;
  date_mode: "write" | "match";
}

// --- pure helpers (unit-tested) ---
export function applyAggChange(rows: MappingRow[], col: string, agg: Agg): MappingRow[] {
  return rows.map((r) => (r.col_letter === col ? { ...r, agg } : r));
}

export function toSavePayload(meta: TemplateMeta, rows: MappingRow[]) {
  return {
    ...meta,
    columns: rows
      .filter((r) => r.enabled && r.tag_id != null)
      .map((r) => ({
        col_letter: r.col_letter,
        tag_id: r.tag_id,
        agg: r.agg,
        source_code: r.source_code,
        enabled: r.enabled,
      })),
  };
}

const AGGS: Agg[] = ["sum", "avg", "min", "max", "last", "delta"];

// fetch helpers — replace bodies with generated client calls from `just gen-client`
async function apiInspect(file: File): Promise<{ sheet_name: string; header_row: number; date_col: string; data_start_row: number; date_mode: "write"; columns: MappingRow[] }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/excel-templates/inspect", { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiList() {
  const res = await fetch("/api/excel-templates");
  return res.json();
}
async function apiSave(payload: ReturnType<typeof toSavePayload>) {
  const res = await fetch("/api/excel-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function fileToB64(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

export default function ExcelTemplates() {
  const qc = useQueryClient();
  const [view, setView] = useState<"list" | "map">("list");
  const [rows, setRows] = useState<MappingRow[]>([]);
  const [meta, setMeta] = useState<TemplateMeta | null>(null);

  const templates = useQuery({ queryKey: ["excel-templates"], queryFn: apiList });

  const saveMut = useMutation({
    mutationFn: () => apiSave(toSavePayload(meta!, rows)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["excel-templates"] });
      setView("list");
    },
  });

  async function onUpload(file: File) {
    const proposal = await apiInspect(file);
    const b64 = await fileToB64(file);
    setMeta({
      name: file.name.replace(/\.xlsx$/i, ""),
      description: "",
      file_b64: b64,
      sheet_name: proposal.sheet_name,
      header_row: proposal.header_row,
      date_col: proposal.date_col,
      data_start_row: proposal.data_start_row,
      date_mode: proposal.date_mode,
    });
    setRows(proposal.columns);
    setView("map");
  }

  function generate(id: number) {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    window.open(`/api/excel-templates/${id}/generate?year=${y}&month=${m}`, "_blank");
  }

  if (view === "map" && meta) {
    return (
      <div className="p-6 text-gray-900 dark:text-gray-100">
        <h1 className="text-xl font-semibold mb-4">Şablon Eşleme — {meta.name}</h1>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b dark:border-gray-700">
              <th>Sütun</th><th>Etiket</th><th>Sensör Kodu</th><th>Tag ID</th><th>Toplama</th><th>Aktif</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.col_letter} className="border-b dark:border-gray-800">
                <td>{r.col_letter}</td>
                <td>{r.label}</td>
                <td>{r.source_code || "—"}</td>
                <td>
                  <input
                    type="number"
                    className="w-20 bg-transparent border rounded px-1"
                    value={r.tag_id ?? ""}
                    onChange={(e) =>
                      setRows((rs) => rs.map((x) => x.col_letter === r.col_letter
                        ? { ...x, tag_id: e.target.value ? Number(e.target.value) : null } : x))}
                  />
                </td>
                <td>
                  <select
                    className="bg-transparent border rounded px-1"
                    value={r.agg}
                    onChange={(e) => setRows((rs) => applyAggChange(rs, r.col_letter, e.target.value as Agg))}
                  >
                    {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={r.enabled}
                    onChange={(e) => setRows((rs) => rs.map((x) => x.col_letter === r.col_letter
                      ? { ...x, enabled: e.target.checked } : x))}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex gap-2">
          <button className="px-3 py-1 rounded bg-blue-600 text-white" onClick={() => saveMut.mutate()}>Kaydet</button>
          <button className="px-3 py-1 rounded border" onClick={() => setView("list")}>İptal</button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 text-gray-900 dark:text-gray-100">
      <h1 className="text-xl font-semibold mb-4">Excel Şablonları</h1>
      <label className="inline-block mb-4 px-3 py-1 rounded bg-blue-600 text-white cursor-pointer">
        + Şablon Yükle
        <input
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
        />
      </label>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b dark:border-gray-700">
            <th>Ad</th><th>Sayfa</th><th>Eşlenen Sütun</th><th>İşlem</th>
          </tr>
        </thead>
        <tbody>
          {(templates.data ?? []).map((t: { id: number; name: string; sheet_name: string; columns: unknown[] }) => (
            <tr key={t.id} className="border-b dark:border-gray-800">
              <td>{t.name}</td>
              <td>{t.sheet_name}</td>
              <td>{t.columns.length}</td>
              <td><button className="px-2 py-0.5 rounded bg-green-600 text-white" onClick={() => generate(t.id)}>Oluştur</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5: Run the vitest to verify it passes**

Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/ExcelTemplates.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 6: Add route + sidebar entry**

In `frontend/src/App.tsx`, import and add a route (match the existing route pattern in that file):

```tsx
import ExcelTemplates from "./pages/ExcelTemplates";
// ...inside the authenticated <Routes>:
<Route path="/excel-templates" element={<ExcelTemplates />} />
```

In `frontend/src/components/Layout.tsx`, add a sidebar nav link next to the other report links (match the existing nav-item markup):

```tsx
{/* alongside existing links */}
<NavLink to="/excel-templates">Excel Şablonları</NavLink>
```

(Use whatever `NavLink`/icon component the neighbouring entries use — copy their exact styling.)

- [ ] **Step 7: Verify frontend builds**

Run: `cd scada-reporter/frontend && pnpm build`
Expected: build succeeds, no TS errors.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/pages/ExcelTemplates.tsx \
        scada-reporter/frontend/src/pages/ExcelTemplates.test.tsx \
        scada-reporter/frontend/src/App.tsx \
        scada-reporter/frontend/src/components/Layout.tsx \
        scada-reporter/frontend/src/api
git commit -m "feat(reports): Excel template UI (upload, mapping confirm, generate)"
```

---

## Task 8: Drift detection on generate

**Files:**
- Modify: `app/services/template_fill/template_inspector.py`
- Modify: `app/api/excel_templates.py`
- Modify: `tests/test_excel_templates_api.py`

Drift = stored `source_code` for a column no longer matches the sensor code currently sitting in that column of the saved template blob (template edited after mapping). Block generate until re-confirmed.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_excel_templates_api.py`:

```python
@pytest.mark.asyncio
async def test_generate_blocks_on_drift(client, seeded_tag, db_session):
    import base64
    from openpyxl import Workbook, load_workbook
    from io import BytesIO

    # save a template mapping col E -> code 410BF103
    payload = {
        "name": "Drift", "description": "", "file_b64": base64.b64encode(_template_bytes()).decode(),
        "sheet_name": "OCAK 2026", "header_row": 2, "date_col": "D", "data_start_row": 3,
        "date_mode": "write",
        "columns": [{"col_letter": "E", "tag_id": seeded_tag.id, "agg": "sum",
                     "source_code": "999XX999", "enabled": True}],  # stored code differs from blob's E2
    }
    save = await client.post("/api/excel-templates", json=payload)
    tpl_id = save.json()["id"]
    gen = await client.post(f"/api/excel-templates/{tpl_id}/generate?year=2026&month=1")
    assert gen.status_code == 409
    assert "drift" in gen.json()["detail"].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_templates_api.py::test_generate_blocks_on_drift -v`
Expected: FAIL — generate returns 200, not 409.

- [ ] **Step 3: Add a drift helper to the inspector**

Append to `app/services/template_fill/template_inspector.py`:

```python
def detect_drift(file_bytes: bytes, sheet_name: str, header_row: int,
                 expected: dict[str, str]) -> list[str]:
    """expected: {col_letter: source_code}. Şablon blob'unda o sütun/satırdaki
    kod değişmişse o sütun harflerini döndürür."""
    from openpyxl.utils import column_index_from_string

    wb = load_workbook(BytesIO(file_bytes), data_only=False)
    ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.worksheets[0]
    drifted = []
    for col_letter, code in expected.items():
        if not code:
            continue
        cell = ws.cell(row=header_row, column=column_index_from_string(col_letter)).value
        if str(cell or "").strip() != code:
            drifted.append(col_letter)
    return drifted
```

- [ ] **Step 4: Enforce drift check in `generate`**

In `app/api/excel_templates.py`, update the `generate` handler to load the template, check drift before filling:

```python
from app.services.template_fill.template_inspector import detect_drift  # add to imports


@router.post("/{template_id}/generate")
async def generate(
    template_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await db.execute(
        select(ExcelTemplate)
        .where(ExcelTemplate.id == template_id)
        .options(selectinload(ExcelTemplate.columns))
    )
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")

    expected = {c.col_letter: c.source_code for c in tpl.columns if c.enabled and c.source_code}
    drifted = detect_drift(tpl.file_blob, tpl.sheet_name, tpl.header_row, expected)
    if drifted:
        raise HTTPException(
            status_code=409,
            detail=f"Şablon değişmiş (drift): sütunlar {', '.join(drifted)}. Eşlemeyi yeniden onaylayın.",
        )

    data = await fill_template(db, template_id, year, month)
    fname = f"rapor_{year}_{month:02d}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
```

(Remove the old `generate` body replaced here. `select`, `selectinload`, `ExcelTemplate` are already imported.)

- [ ] **Step 5: Run the drift test + full API suite**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest tests/test_excel_templates_api.py -v`
Expected: PASS (3 tests, incl. drift). The earlier `test_save_and_generate_roundtrip` still passes (its stored `source_code` matches the blob).

- [ ] **Step 6: Surface drift in the UI**

In `frontend/src/pages/ExcelTemplates.tsx`, in `generate`, handle a 409 by alerting + reopening map view. Replace the `window.open` approach with a fetch so status is observable:

```tsx
async function generate(id: number) {
  const now = new Date();
  const res = await fetch(
    `/api/excel-templates/${id}/generate?year=${now.getFullYear()}&month=${now.getMonth() + 1}`,
    { method: "POST" },
  );
  if (res.status === 409) {
    const body = await res.json();
    alert(body.detail);
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `rapor_${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, "0")}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 7: Run full checks**

Run: `cd scada-reporter/backend && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check app tests`
Run: `cd scada-reporter/frontend && pnpm vitest run src/pages/ExcelTemplates.test.tsx && pnpm build`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/template_inspector.py \
        scada-reporter/backend/app/api/excel_templates.py \
        scada-reporter/backend/tests/test_excel_templates_api.py \
        scada-reporter/frontend/src/pages/ExcelTemplates.tsx
git commit -m "feat(reports): drift detection blocks generate when template edited"
```

---

## Done criteria

- `just test` (backend) green incl. new suites: `test_daily_rollup`, `test_template_inspector`, `test_fill_engine`, `test_excel_template_model`, `test_excel_templates_api`.
- `just lint` clean.
- Frontend builds; `ExcelTemplates.test.tsx` green.
- Manual smoke: upload `gunluk_rapor.xlsx`-style single-sheet template → confirm mapping → generate current month → downloaded xlsx has daily values in the right cells, format preserved, unmapped (weather) columns blank.
- Alembic single head `f1a2b3c4d5e6`.

## Out of scope (per spec)
Historical-month backfill, native chart generation, in-place master-workbook edit, `{{token}}` substitution, PDF output, sub-project B (ad-hoc config reports — separate plan; reuses `daily_values`).
