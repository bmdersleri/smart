# Facility Variables — Excel Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Excel template columns bind to facility variables (not just raw tags), so a column is filled by the backend variable engine — series down rows or a reduced scalar into one cell — while every existing `tag_id + agg` column keeps working unchanged.

**Architecture:** Extend `excel_template_columns` with variable-aware binding fields (additive, backward-compatible). A new `resolver.evaluate_variable` gives one shared ref-resolving entry point (preview + binding use it, so they cannot diverge). A `facility_variable_binding` service resolves a column to either a `{day_no: value}` dict (column target) or a scalar (cell target). `fill_engine` dispatches on `source_type`: tag → existing `daily_values`; variable → binding resolver. A dangling-binding guard blocks deactivating a variable that an enabled column references, and surfaces a visible warning at fill time instead of writing blank cells. Unit compatibility is checked conservatively at variable create/update.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Alembic, openpyxl, pytest-asyncio, SQLite (dev/test) / PostgreSQL+TimescaleDB (prod).

## Global Constraints

- Python baseline is **3.14** — never lower it.
- Tests run on **in-memory SQLite** via the shared `db_engine`/`db_session`/`client` fixtures in `tests/conftest.py`; an autouse fixture clears all tables before each test — never rely on cross-test data.
- All new code must be ruff-clean, mypy-clean, format-clean, and bandit-zero **on the new/changed files**. `just check`'s bandit step currently exits 1 on **pre-existing** findings in unrelated files (`dashboard.py`, `s7_collector.py`, `config.py`, `metrics.py`, `grafana_templates.py`, `scheduler.py`) — that is not your concern. Verify your files directly: `python -m ruff check <f> && python -m mypy <f> && python -m ruff format --check <f> && python -m bandit -q <f>`.
- Run tests **serially** with `-n0` (e.g. `python -m pytest tests/test_x.py -n0`); the parallel `-n auto` run has a known-flaky PDF test unrelated to this work.
- Comments/strings in this codebase are **Turkish**; match the surrounding style.
- **Backward compatibility is non-negotiable:** every existing `excel_template_columns` row (no `source_type`) must behave exactly as before. The migration sets `server_default='tag'` / `target_mode` `'column'`; the fill path treats absent/`tag` source as the legacy path. `tests/test_fill_engine.py` and `tests/test_excel_templates_api.py` must stay green.
- **One aggregation primitive / one tz offset:** variable-backed fill must reuse `evaluate_variable` (which reuses the Plan-1 engine + `daily_rollup.reduce_values`) at the same `REPORT_TZ_OFFSET_HOURS` the tag path uses. No second bucketing or rounding implementation.
- Migration head to chain from: **`e2f3a4b5c6d7`** (Plan 1's migration).

## Context from Plan 1 (already shipped on master)

- Models: `app/models/facility_variable.py` — `FacilityVariable` (fields incl. `kind`, `unit`, `expression_json`, `quality_policy`, `is_active`, `version`), `FacilityVariableDependency`.
- `app/services/facility_variables/engine.py` — `EvalResult(kind, scalar, series)`, `async evaluate(db, node, *, start, end, grain, tz_offset_hours, resolve_ref) -> EvalResult`. `evaluate` is model-free.
- `app/services/facility_variables/preview.py` — `preview_variable(...)` currently holds an **inline** `resolve_ref` closure that resolves a `ref` op against active variables. Task 1 extracts that into a shared helper.
- `app/services/facility_variables/service.py` — `create_variable`, `update_variable` (does **not** accept `kind`; kind is immutable post-create), `deactivate_variable`, `VariableError`.
- `app/services/template_fill/daily_rollup.py` — `daily_values(db, tag_id, year, month, agg, tz_offset_hours) -> dict[int, float]`, `reduce_values(values, agg)`.
- `app/services/template_fill/fill_engine.py` — `fill_template(db, template_id, year, month) -> bytes` (the month-based loop that writes `daily_values` into `day_to_row`).
- `app/models/excel_template.py` — `ExcelTemplateColumn` has `col_letter, tag_id, agg, source_code, enabled`.
- `app/api/excel_templates.py` — `ColumnIn`/`ColumnOut`/`_to_out`/`create_template`/`generate` (the generate route already calls `fill_template`).

**Kind immutability note:** the spec's "output-shape lock while bound" guard is already satisfied — `update_variable` cannot change `kind` (no parameter for it). This plan therefore does **not** add a kind-change guard; it only adds the deactivation (dangling-binding) guard.

## Plan Roadmap (this is Plan 2 of 5)

1. Backend Foundation ✅ (shipped)
2. **Excel binding** ← this plan
3. Advanced reports + archive version stamping
4. Frontend (list, wizard, expression builder, preview UI, Excel-mapping UX, i18n ×5, permission labels)
5. Seeding high-value variables + `gunluk_rapor.xlsx` column migration

**Still deferred (NOT in this plan):** `quality_policy` leaf-read filtering + PostgreSQL continuous-aggregate routing for the engine (a separate perf/correctness hardening plan, since both dialects must change together and it is orthogonal to binding); all UI (Plan 4). This plan keeps the engine on the Plan-1 raw-bucketing path; the parity test still guarantees correctness.

---

### Task 1: Shared `evaluate_variable` (DRY ref resolution)

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/resolver.py`
- Modify: `scada-reporter/backend/app/services/facility_variables/preview.py` (replace its inline `resolve_ref` with the shared helper)
- Test: `scada-reporter/backend/tests/test_facility_variable_resolver.py`

**Interfaces:**
- Consumes: `engine.EvalResult`, `engine.evaluate`; `models.FacilityVariable`.
- Produces: `async evaluate_variable(db, var, *, start, end, grain, tz_offset_hours) -> EvalResult` — parses `var.expression_json`, evaluates it, resolving every `ref` op against **active** variables (inactive/missing → `EvalResult(kind="scalar", scalar=None)`), recursively at the same window/grain/tz. Stored variables are acyclic (cycles rejected at write time in Plan 1), so recursion terminates.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_resolver.py`:

```python
from datetime import datetime

import pytest

from app.services.facility_variables.resolver import evaluate_variable
from app.services.facility_variables.service import create_variable


async def _make(db, code, expression, kind="scalar"):
    return await create_variable(
        db, code=code, name=code, description="", kind=kind, unit="",
        expression=expression, null_policy="skip", quality_policy="good_only",
        default_time_grain="day", value_type="number", created_by=1,
    )


JUNE = (datetime(2026, 6, 1), datetime(2026, 7, 1))


@pytest.mark.asyncio
async def test_evaluate_const_variable(db_session):
    var = await _make(db_session, "c", {"op": "const", "value": 7.0})
    res = await evaluate_variable(
        db_session, var, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.kind == "scalar"
    assert res.scalar == 7.0


@pytest.mark.asyncio
async def test_ref_resolves_active_variable(db_session):
    a = await _make(db_session, "a", {"op": "const", "value": 5.0})
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    res = await evaluate_variable(
        db_session, b, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.scalar == 5.0


@pytest.mark.asyncio
async def test_ref_to_inactive_yields_none(db_session):
    from app.services.facility_variables.service import deactivate_variable

    a = await _make(db_session, "a", {"op": "const", "value": 5.0})
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    await deactivate_variable(db_session, a.id)
    res = await evaluate_variable(
        db_session, b, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0
    )
    assert res.scalar is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_facility_variable_resolver.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.resolver'`.

- [ ] **Step 3: Write the resolver**

Create `app/services/facility_variables/resolver.py`:

```python
"""Bir tesis değişkenini değerlendirir, ref'leri aktif değişkenlere çözer.

preview ve Excel binding ortak bu giriş noktasını kullanır — iki ayrı ref
çözüm yolu olmasın (sapma riski). Saklanan değişkenler döngüsüzdür (döngü
yazma anında reddedilir), bu yüzden özyineleme sonlanır.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.engine import EvalResult, evaluate


async def evaluate_variable(
    db: AsyncSession,
    var: FacilityVariable,
    *,
    start: datetime,
    end: datetime,
    grain: str,
    tz_offset_hours: int,
) -> EvalResult:
    expression = json.loads(var.expression_json)

    async def resolve_ref(variable_id: int) -> EvalResult:
        ref_var = await db.get(FacilityVariable, variable_id)
        if ref_var is None or not ref_var.is_active:
            return EvalResult(kind="scalar", scalar=None)
        return await evaluate_variable(
            db, ref_var, start=start, end=end, grain=grain, tz_offset_hours=tz_offset_hours
        )

    return await evaluate(
        db, expression, start=start, end=end, grain=grain,
        tz_offset_hours=tz_offset_hours, resolve_ref=resolve_ref,
    )
```

- [ ] **Step 4: Refactor `preview.py` to use it**

In `app/services/facility_variables/preview.py`, replace the inline `resolve_ref` closure + the direct `evaluate(...)` call inside `preview_variable` with a single call to the shared helper. The body of `preview_variable` after `check_preview_bounds(...)` becomes:

```python
    result = await evaluate_variable(
        db, var, start=start, end=end, grain=grain, tz_offset_hours=tz_offset_hours
    )
```

Add the import at the top of `preview.py`:

```python
from app.services.facility_variables.resolver import evaluate_variable
```

Remove the now-unused imports in `preview.py` if they become unused (`json` is still used? — `preview_variable` no longer parses `expression_json` itself, so remove `import json` only if nothing else uses it; `evaluate`/`EvalResult` imports are no longer needed in `preview.py` — remove them). Run ruff to confirm no unused imports remain.

- [ ] **Step 5: Run resolver + preview tests to verify both pass**

Run: `python -m pytest tests/test_facility_variable_resolver.py tests/test_facility_variable_preview.py -n0`
Expected: PASS (resolver: 3; preview: 5 — the refactor must not change preview behavior).

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/resolver.py \
        scada-reporter/backend/app/services/facility_variables/preview.py \
        scada-reporter/backend/tests/test_facility_variable_resolver.py
git commit -m "refactor(facility-vars): extract shared evaluate_variable; preview reuses it"
```

---

### Task 2: Extend `excel_template_columns` (model + migration)

**Files:**
- Modify: `scada-reporter/backend/app/models/excel_template.py`
- Create: `scada-reporter/backend/alembic/versions/f3a4b5c6d7e8_excel_column_variable_binding.py`
- Test: `scada-reporter/backend/tests/test_excel_template_model.py` (add a binding-fields test)

**Interfaces:**
- Produces — `ExcelTemplateColumn` gains:
  - `source_type: str` (`tag|variable`, default `"tag"`, NOT NULL, server_default `'tag'`)
  - `variable_id: int | None` (FK→`facility_variables.id`, ondelete `SET NULL`, nullable)
  - `write_mode: str | None` (`series|reduce`, nullable)
  - `reduce_op: str | None` (`sum|avg|min|max|last`, nullable)
  - `target_mode: str` (`column|cell`, default `"column"`, NOT NULL, server_default `'column'`)
  - `target_cell: str | None` (A1 ref, nullable, `String(8)`)
  - `variable_code_snapshot: str | None` (`String(64)`, nullable)

- [ ] **Step 1: Write the failing test**

Append to `scada-reporter/backend/tests/test_excel_template_model.py`:

```python
@pytest.mark.asyncio
async def test_column_variable_binding_fields(db_session):
    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn

    tpl = ExcelTemplate(
        name="vbind", description="", file_blob=b"x", sheet_name="S",
        header_row=1, date_col="A", data_start_row=2,
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter="K", source_type="variable", variable_id=None,
            write_mode="reduce", reduce_op="sum", target_mode="cell",
            target_cell="K5", variable_code_snapshot="var_baat_giris_toplam",
        )
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl, attribute_names=["columns"])

    col = tpl.columns[0]
    assert col.source_type == "variable"
    assert col.target_mode == "cell"
    assert col.target_cell == "K5"
    assert col.variable_code_snapshot == "var_baat_giris_toplam"


@pytest.mark.asyncio
async def test_column_defaults_to_tag_source(db_session):
    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn

    tpl = ExcelTemplate(
        name="legacy", description="", file_blob=b"x", sheet_name="S",
        header_row=1, date_col="A", data_start_row=2,
    )
    tpl.columns = [ExcelTemplateColumn(col_letter="E", tag_id=None, agg="sum")]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl, attribute_names=["columns"])

    col = tpl.columns[0]
    assert col.source_type == "tag"
    assert col.target_mode == "column"
```

(If `test_excel_template_model.py` does not already `import pytest` / define a `db_session`-using async style, match the existing file's imports and decorators.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_excel_template_model.py -k "variable_binding or defaults_to_tag" -n0`
Expected: FAIL — `TypeError: 'source_type' is an invalid keyword argument` (or AttributeError on `col.source_type`).

- [ ] **Step 3: Extend the model**

In `app/models/excel_template.py`, add to `ExcelTemplateColumn` (after `enabled`):

```python
    source_type: Mapped[str] = mapped_column(String(8), default="tag", nullable=False)  # tag|variable
    variable_id: Mapped[int | None] = mapped_column(
        ForeignKey("facility_variables.id", ondelete="SET NULL"), nullable=True
    )
    write_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)  # series|reduce
    reduce_op: Mapped[str | None] = mapped_column(String(8), nullable=True)  # sum|avg|min|max|last
    target_mode: Mapped[str] = mapped_column(String(8), default="column", nullable=False)  # column|cell
    target_cell: Mapped[str | None] = mapped_column(String(8), nullable=True)
    variable_code_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

(`String` and `ForeignKey` are already imported in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_excel_template_model.py -n0`
Expected: PASS (existing model tests + 2 new).

- [ ] **Step 5: Write the Alembic migration**

Create `alembic/versions/f3a4b5c6d7e8_excel_column_variable_binding.py`:

```python
"""excel_template_columns variable-binding fields

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-29 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "excel_template_columns",
        sa.Column("source_type", sa.String(length=8), nullable=False, server_default="tag"),
    )
    op.add_column(
        "excel_template_columns", sa.Column("variable_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "excel_template_columns", sa.Column("write_mode", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns", sa.Column("reduce_op", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns",
        sa.Column("target_mode", sa.String(length=8), nullable=False, server_default="column"),
    )
    op.add_column(
        "excel_template_columns", sa.Column("target_cell", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "excel_template_columns",
        sa.Column("variable_code_snapshot", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_excel_col_variable_id",
        "excel_template_columns",
        "facility_variables",
        ["variable_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_excel_col_variable_id", "excel_template_columns", type_="foreignkey")
    for col in (
        "variable_code_snapshot",
        "target_cell",
        "target_mode",
        "reduce_op",
        "write_mode",
        "variable_id",
        "source_type",
    ):
        op.drop_column("excel_template_columns", col)
```

> **SQLite note:** `op.create_foreign_key` is a no-op/limited on SQLite (no `ALTER ... ADD CONSTRAINT`). That is fine — dev/test uses `Base.metadata.create_all` (which builds the FK from the model), and prod is PostgreSQL where the migration FK applies. If `alembic upgrade head` on a SQLite dev DB errors on the FK step, wrap the `create_foreign_key` in `if op.get_bind().dialect.name != "sqlite":` and the matching `drop_constraint` likewise.

- [ ] **Step 6: Verify migration applies (PostgreSQL path) / model parity (SQLite)**

Run: `python -m alembic heads`
Expected: `f3a4b5c6d7e8 (head)`. (Full `upgrade head` against a real PG DB is the prod check; on SQLite dev the schema comes from `create_all`, already exercised by the model test in Step 4.)

- [ ] **Step 7: Confirm legacy fill/api tests still green**

Run: `python -m pytest tests/test_fill_engine.py tests/test_excel_templates_api.py -n0`
Expected: PASS — new columns are additive with server defaults; existing behavior unchanged.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/backend/app/models/excel_template.py \
        scada-reporter/backend/alembic/versions/f3a4b5c6d7e8_excel_column_variable_binding.py \
        scada-reporter/backend/tests/test_excel_template_model.py
git commit -m "feat(excel-binding): extend excel_template_columns with variable-binding fields"
```

---

### Task 3: Binding resolver

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/binding.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_binding.py`

**Interfaces:**
- Consumes: `daily_rollup.daily_values`, `daily_rollup.reduce_values`, `resolver.evaluate_variable`, `models.FacilityVariable`, `models.ExcelTemplateColumn`.
- Produces:
  - `@dataclass class BindingResult: kind: str` (`"column"|"cell"`)`, days: dict[int, float], scalar: float | None, warnings: list[str]`
  - `async resolve_column(db, col, year, month, tz_offset_hours) -> BindingResult` — dispatch:
    - `source_type == "tag"` (or default): `daily_values(...)` → `BindingResult("column", days, None, [])`.
    - `source_type == "variable"`: load the variable; if missing/inactive → `BindingResult` with empty data + a warning. Else `evaluate_variable(...)` over the month at day grain:
      - cell target (`target_mode == "cell"` or `write_mode == "reduce"` or `var.kind == "scalar"`): collapse to scalar — `res.scalar` if scalar-shaped, else `reduce_values(list(series_values_non_null), col.reduce_op or "last")` — `BindingResult("cell", {}, scalar, warnings)`.
      - column target (series, `target_mode == "column"`): `days = {k.day: v for k, v in res.series.items() if v is not None}` → `BindingResult("column", days, None, warnings)`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_binding.py`:

```python
from datetime import datetime

import pytest

from app.models.excel_template import ExcelTemplateColumn
from app.models.tag import Tag, TagReading
from app.services.facility_variables.binding import BindingResult, resolve_column
from app.services.facility_variables.service import create_variable


async def _tag_with_readings(db, name, rows):
    tag = Tag(node_id=name, name=name, unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    for ts, val in rows:
        db.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db.commit()
    return tag


@pytest.mark.asyncio
async def test_tag_column_uses_daily_values(db_session):
    tag = await _tag_with_readings(
        db_session, "T",
        [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)],
    )
    col = ExcelTemplateColumn(col_letter="E", source_type="tag", tag_id=tag.id, agg="delta")
    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "column"
    assert res.days[1] == 40.0


@pytest.mark.asyncio
async def test_variable_series_column(db_session):
    tag = await _tag_with_readings(
        db_session, "T",
        [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)],
    )
    var = await create_variable(
        db_session, code="v_series", name="v", description="", kind="series", unit="m3/gun",
        expression={"op": "series", "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta", "grain": "day", "window": "month"},
        null_policy="skip", quality_policy="good_only", default_time_grain="day",
        value_type="number", created_by=1,
    )
    col = ExcelTemplateColumn(
        col_letter="K", source_type="variable", variable_id=var.id,
        write_mode="series", target_mode="column",
    )
    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "column"
    assert res.days[1] == 40.0


@pytest.mark.asyncio
async def test_variable_reduce_to_cell(db_session):
    tag = await _tag_with_readings(
        db_session, "T",
        [
            (datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0),
            (datetime(2026, 6, 2, 0), 40.0), (datetime(2026, 6, 2, 23), 80.0),
        ],
    )
    var = await create_variable(
        db_session, code="v_series2", name="v", description="", kind="series", unit="m3/gun",
        expression={"op": "series", "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta", "grain": "day", "window": "month"},
        null_policy="skip", quality_policy="good_only", default_time_grain="day",
        value_type="number", created_by=1,
    )
    col = ExcelTemplateColumn(
        col_letter="K", source_type="variable", variable_id=var.id,
        write_mode="reduce", reduce_op="avg", target_mode="cell", target_cell="K5",
    )
    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.kind == "cell"
    assert res.scalar == 40.0  # avg of daily deltas 40, 40


@pytest.mark.asyncio
async def test_inactive_variable_warns(db_session):
    from app.services.facility_variables.service import deactivate_variable

    var = await create_variable(
        db_session, code="v_off", name="v", description="", kind="scalar", unit="",
        expression={"op": "const", "value": 1.0}, null_policy="skip",
        quality_policy="good_only", default_time_grain="day", value_type="number", created_by=1,
    )
    await deactivate_variable(db_session, var.id)
    col = ExcelTemplateColumn(
        col_letter="K", source_type="variable", variable_id=var.id, target_mode="cell",
    )
    res = await resolve_column(db_session, col, 2026, 6, tz_offset_hours=0)
    assert res.warnings
    assert res.scalar is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_binding.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.binding'`.

- [ ] **Step 3: Write the binding resolver**

Create `app/services/facility_variables/binding.py`:

```python
"""Excel sütununu değere çözer: tag → daily_values, variable → engine.

Çıktı şekli sözleşmesi (Plan 1): kolon hedefi {gün_no: değer}, hücre hedefi tek
scalar. Verisi olmayan gün anahtarsız (0 uydurma yok). Pasif/eksik değişken
sessiz boş yazmaz — görünür uyarı döndürür.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.excel_template import ExcelTemplateColumn
from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.resolver import evaluate_variable
from app.services.template_fill.daily_rollup import daily_values, reduce_values


@dataclass
class BindingResult:
    kind: str  # column | cell
    days: dict[int, float] = field(default_factory=dict)
    scalar: float | None = None
    warnings: list[str] = field(default_factory=list)


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day) + (datetime(year, month, last_day) - datetime(year, month, last_day))
    # end = first instant of next month
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _is_cell_target(col: ExcelTemplateColumn, var: FacilityVariable) -> bool:
    return col.target_mode == "cell" or col.write_mode == "reduce" or var.kind == "scalar"


async def resolve_column(
    db: AsyncSession,
    col: ExcelTemplateColumn,
    year: int,
    month: int,
    tz_offset_hours: int,
) -> BindingResult:
    # Eski yol: tag + agg → değişmeden daily_values.
    if col.source_type != "variable":
        if col.tag_id is None:
            return BindingResult(kind="column")
        days = await daily_values(db, col.tag_id, year, month, col.agg, tz_offset_hours)
        return BindingResult(kind="column", days=days)

    var = await db.get(FacilityVariable, col.variable_id) if col.variable_id else None
    if var is None or not var.is_active:
        kind = "cell" if col.target_mode == "cell" else "column"
        return BindingResult(
            kind=kind,
            warnings=[f"{col.col_letter}: bağlı değişken pasif veya bulunamadı"],
        )

    start, end = _month_bounds(year, month)
    res = await evaluate_variable(
        db, var, start=start, end=end, grain="day", tz_offset_hours=tz_offset_hours
    )

    if _is_cell_target(col, var):
        if res.kind == "scalar":
            scalar = res.scalar
        else:
            vals = [v for v in (res.series or {}).values() if v is not None]
            scalar = reduce_values(vals, col.reduce_op or "last")
        return BindingResult(kind="cell", scalar=scalar)

    days = {k.day: v for k, v in (res.series or {}).items() if v is not None}
    return BindingResult(kind="column", days=days)
```

(Clean up the redundant `end` line — keep only the `datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)` form; `calendar` import may then be unused, remove it if so. Run ruff to confirm.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_binding.py -n0`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/binding.py \
        scada-reporter/backend/tests/test_facility_variable_binding.py
git commit -m "feat(excel-binding): column→value resolver for tag and variable sources"
```

---

### Task 4: `fill_engine` integration

**Files:**
- Modify: `scada-reporter/backend/app/services/template_fill/fill_engine.py`
- Test: `scada-reporter/backend/tests/test_fill_engine.py` (add variable-backed + mixed tests)

**Interfaces:**
- Consumes: `binding.resolve_column`, `binding.BindingResult`.
- Produces: `fill_template(db, template_id, year, month) -> bytes` (unchanged signature) now also fills variable-backed columns. Column-target binding → writes `days[day]` into `col_letter{row}` via `day_to_row` (same as tag). Cell-target binding → writes `scalar` into `target_cell` once. A binding's `warnings` are collected and logged (no exception, no blank-silent).

- [ ] **Step 1: Write the failing test**

Append to `scada-reporter/backend/tests/test_fill_engine.py` (reuse the file's existing seeding helpers / `Tag` import style):

```python
@pytest.mark.asyncio
async def test_fill_variable_series_column(db_session):
    from openpyxl import load_workbook
    from io import BytesIO

    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
    from app.models.tag import Tag, TagReading
    from app.services.facility_variables.service import create_variable
    from app.services.template_fill.fill_engine import fill_template

    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 0), value=0.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 23), value=40.0))
    await db_session.commit()

    var = await create_variable(
        db_session, code="v_fill", name="v", description="", kind="series", unit="m3/gun",
        expression={"op": "series", "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta", "grain": "day", "window": "month"},
        null_policy="skip", quality_policy="good_only", default_time_grain="day",
        value_type="number", created_by=1,
    )

    wb = Workbook()  # Workbook imported at top of test file
    ws = wb.active
    ws.title = "S"
    buf = BytesIO()
    wb.save(buf)

    tpl = ExcelTemplate(
        name="vf", description="", file_blob=buf.getvalue(), sheet_name="S",
        header_row=1, date_col="A", data_start_row=2, date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter="K", source_type="variable", variable_id=var.id,
            write_mode="series", target_mode="column", enabled=True,
        )
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)

    out = await fill_template(db_session, tpl.id, 2026, 6)
    rwb = load_workbook(BytesIO(out))
    rws = rwb["S"]
    # day 1 → data_start_row (2): K2 == 40.0
    assert rws["K2"].value == 40.0


@pytest.mark.asyncio
async def test_fill_variable_reduce_cell(db_session):
    from openpyxl import load_workbook
    from io import BytesIO

    from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
    from app.models.tag import Tag, TagReading
    from app.services.facility_variables.service import create_variable
    from app.services.template_fill.fill_engine import fill_template

    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    for ts, v in (
        (datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0),
        (datetime(2026, 6, 2, 0), 40.0), (datetime(2026, 6, 2, 23), 80.0),
    ):
        db_session.add(TagReading(tag_id=tag.id, timestamp=ts, value=v))
    await db_session.commit()

    var = await create_variable(
        db_session, code="v_red", name="v", description="", kind="series", unit="m3/gun",
        expression={"op": "series", "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta", "grain": "day", "window": "month"},
        null_policy="skip", quality_policy="good_only", default_time_grain="day",
        value_type="number", created_by=1,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    buf = BytesIO()
    wb.save(buf)

    tpl = ExcelTemplate(
        name="vr", description="", file_blob=buf.getvalue(), sheet_name="S",
        header_row=1, date_col="A", data_start_row=2, date_mode="write",
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter="K", source_type="variable", variable_id=var.id,
            write_mode="reduce", reduce_op="avg", target_mode="cell", target_cell="M5",
            enabled=True,
        )
    ]
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)

    out = await fill_template(db_session, tpl.id, 2026, 6)
    rwb = load_workbook(BytesIO(out))
    rws = rwb["S"]
    assert rws["M5"].value == 40.0  # avg(40, 40)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fill_engine.py -k "variable" -n0`
Expected: FAIL — the current `fill_template` skips columns whose `tag_id is None` (variable columns have `tag_id=None`), so `K2`/`M5` are empty → assertion fails.

- [ ] **Step 3: Integrate binding into `fill_template`**

In `app/services/template_fill/fill_engine.py`, add the import and replace the column loop. New imports near the top:

```python
import logging

from app.services.facility_variables.binding import resolve_column

logger = logging.getLogger(__name__)
```

Replace the existing `for col in tpl.columns:` block with:

```python
    for col in tpl.columns:
        if not col.enabled:
            continue
        source_type = getattr(col, "source_type", "tag")
        if source_type != "variable" and col.tag_id is None:
            continue

        result = await resolve_column(db, col, year, month, tz_offset_hours=offset)
        for w in result.warnings:
            logger.warning("Excel fill binding uyarısı: %s", w)

        if result.kind == "cell":
            if col.target_cell and result.scalar is not None:
                ws[col.target_cell] = result.scalar
            continue

        for day, value in result.days.items():
            row = day_to_row.get(day)
            if row is not None:
                ws[f"{col.col_letter}{row}"] = value
```

(`offset = settings.REPORT_TZ_OFFSET_HOURS` is already computed earlier in `fill_template`; keep it.)

- [ ] **Step 4: Run tests to verify they pass (incl. no regression)**

Run: `python -m pytest tests/test_fill_engine.py -n0`
Expected: PASS — the 6 existing tag-path tests stay green (they hit the `source_type != "variable"` branch → unchanged `daily_values` write via `result.days`), plus the 2 new variable tests.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/fill_engine.py \
        scada-reporter/backend/tests/test_fill_engine.py
git commit -m "feat(excel-binding): fill variable-backed columns (series rows / reduced cell)"
```

---

### Task 5: Dangling-binding guard

**Files:**
- Modify: `scada-reporter/backend/app/services/facility_variables/service.py`
- Modify: `scada-reporter/backend/app/api/facility_variables.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_binding_guard.py`

**Interfaces:**
- Produces:
  - `async columns_referencing_variable(db, var_id) -> list[ExcelTemplateColumn]` (service) — enabled columns with `source_type="variable"` and `variable_id == var_id`.
  - `deactivate_variable(db, var_id, *, force: bool = False)` — raises `VariableError` if referenced by an enabled column and not `force`.
  - API `DELETE /facility-variables/{id}` returns **409** with the referencing template ids when blocked; `?force=true` overrides.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_binding_guard.py`:

```python
import pytest

from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.services.facility_variables.service import (
    VariableError,
    columns_referencing_variable,
    create_variable,
    deactivate_variable,
)


async def _var(db, code):
    return await create_variable(
        db, code=code, name=code, description="", kind="scalar", unit="",
        expression={"op": "const", "value": 1.0}, null_policy="skip",
        quality_policy="good_only", default_time_grain="day", value_type="number", created_by=1,
    )


async def _bind(db, var_id, enabled=True):
    tpl = ExcelTemplate(
        name=f"t{var_id}", description="", file_blob=b"x", sheet_name="S",
        header_row=1, date_col="A", data_start_row=2,
    )
    tpl.columns = [
        ExcelTemplateColumn(
            col_letter="K", source_type="variable", variable_id=var_id,
            target_mode="cell", enabled=enabled,
        )
    ]
    db.add(tpl)
    await db.commit()


@pytest.mark.asyncio
async def test_referencing_columns_found(db_session):
    var = await _var(db_session, "rv")
    await _bind(db_session, var.id)
    cols = await columns_referencing_variable(db_session, var.id)
    assert len(cols) == 1


@pytest.mark.asyncio
async def test_deactivate_blocked_when_referenced(db_session):
    var = await _var(db_session, "rv2")
    await _bind(db_session, var.id)
    with pytest.raises(VariableError, match="kullan|referenc|bağlı"):
        await deactivate_variable(db_session, var.id)


@pytest.mark.asyncio
async def test_deactivate_force_overrides(db_session):
    var = await _var(db_session, "rv3")
    await _bind(db_session, var.id)
    out = await deactivate_variable(db_session, var.id, force=True)
    assert out.is_active is False


@pytest.mark.asyncio
async def test_deactivate_allowed_when_only_disabled_column(db_session):
    var = await _var(db_session, "rv4")
    await _bind(db_session, var.id, enabled=False)
    out = await deactivate_variable(db_session, var.id)
    assert out.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_binding_guard.py -n0`
Expected: FAIL with `ImportError: cannot import name 'columns_referencing_variable'`.

- [ ] **Step 3: Add the guard to the service**

In `app/services/facility_variables/service.py`, add the import and functions:

```python
from app.models.excel_template import ExcelTemplateColumn
```

```python
async def columns_referencing_variable(
    db: AsyncSession, var_id: int
) -> list[ExcelTemplateColumn]:
    """var_id'ye bağlı, etkin Excel sütunları."""
    rows = await db.execute(
        select(ExcelTemplateColumn).where(
            ExcelTemplateColumn.source_type == "variable",
            ExcelTemplateColumn.variable_id == var_id,
            ExcelTemplateColumn.enabled.is_(True),
        )
    )
    return list(rows.scalars().all())
```

Replace the existing `deactivate_variable` with:

```python
async def deactivate_variable(
    db: AsyncSession, var_id: int, *, force: bool = False
) -> FacilityVariable:
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise VariableError("Değişken bulunamadı")
    if not force:
        refs = await columns_referencing_variable(db, var_id)
        if refs:
            tpl_ids = sorted({c.template_id for c in refs})
            raise VariableError(
                f"Değişken Excel şablonlarınca kullanılıyor (template {tpl_ids}); "
                "önce bağlamayı kaldırın veya force kullanın"
            )
    var.is_active = False
    await db.commit()
    await db.refresh(var)
    return var
```

- [ ] **Step 4: Wire `force` into the API DELETE route**

In `app/api/facility_variables.py`, change the soft-delete route to accept `force` and map the guard to 409:

```python
@router.delete("/{var_id}", status_code=204)
async def soft_delete(
    var_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm(PERM_FACILITY_VARIABLE_DELETE)),
    _w: None = Depends(require_writable),
):
    try:
        await deactivate_variable(db, var_id, force=force)
    except VariableError as e:
        msg = str(e)
        if "bulunamadı" in msg:
            raise HTTPException(404, msg) from e
        raise HTTPException(409, msg) from e
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_facility_variable_binding_guard.py tests/test_facility_variables_api.py tests/test_facility_variable_service.py -n0`
Expected: PASS — new guard tests; the existing API `test_soft_delete` (variable with no binding) still returns 204; service tests unchanged.

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/service.py \
        scada-reporter/backend/app/api/facility_variables.py \
        scada-reporter/backend/tests/test_facility_variable_binding_guard.py
git commit -m "feat(excel-binding): block deactivating a variable bound by an enabled column"
```

---

### Task 6: Expose binding fields in the Excel templates API

**Files:**
- Modify: `scada-reporter/backend/app/api/excel_templates.py`
- Test: `scada-reporter/backend/tests/test_excel_templates_api.py` (add a variable-binding round-trip + validation test)

**Interfaces:**
- Produces — `ColumnIn`/`ColumnOut` gain `source_type` (default `"tag"`), `variable_id` (None), `write_mode` (None), `reduce_op` (None), `target_mode` (default `"column"`), `target_cell` (None), `variable_code_snapshot` (None). `_to_out` and `create_template` round-trip them. Validation in `create_template`: a column must have **exactly one** of `tag_id` / `variable_id` non-null (per its `source_type`); `write_mode == "series"` requires `target_mode == "column"`; `target_mode == "cell"` requires `target_cell`. Violations → HTTP 422.

- [ ] **Step 1: Write the failing test**

Append to `scada-reporter/backend/tests/test_excel_templates_api.py`:

```python
@pytest.mark.asyncio
async def test_variable_binding_roundtrip(client, db_session):
    import base64

    from app.services.facility_variables.service import create_variable

    var = await create_variable(
        db_session, code="v_api", name="v", description="", kind="scalar", unit="m3/gun",
        expression={"op": "const", "value": 1.0}, null_policy="skip",
        quality_policy="good_only", default_time_grain="day", value_type="number", created_by=1,
    )
    payload = {
        "name": "vbind-api", "description": "", "file_b64": base64.b64encode(_template_bytes()).decode(),
        "sheet_name": "OCAK 2026", "header_row": 2, "date_col": "D", "data_start_row": 3,
        "date_mode": "write",
        "columns": [
            {
                "col_letter": "K", "source_type": "variable", "variable_id": var.id,
                "write_mode": "reduce", "reduce_op": "sum", "target_mode": "cell",
                "target_cell": "K5", "variable_code_snapshot": "v_api", "enabled": True,
            }
        ],
    }
    resp = await client.post("/api/excel-templates", json=payload)
    assert resp.status_code == 201
    col = resp.json()["columns"][0]
    assert col["source_type"] == "variable"
    assert col["variable_id"] == var.id
    assert col["target_cell"] == "K5"


@pytest.mark.asyncio
async def test_variable_column_rejects_both_sources(client):
    import base64

    payload = {
        "name": "bad-both", "description": "", "file_b64": base64.b64encode(_template_bytes()).decode(),
        "sheet_name": "OCAK 2026", "header_row": 2, "date_col": "D", "data_start_row": 3,
        "date_mode": "write",
        "columns": [
            {"col_letter": "K", "source_type": "variable", "variable_id": 1, "tag_id": 9, "enabled": True}
        ],
    }
    resp = await client.post("/api/excel-templates", json=payload)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_excel_templates_api.py -k "variable" -n0`
Expected: FAIL — `ColumnIn` has no `source_type`/`variable_id` (Pydantic ignores unknown keys, so the round-trip assertion on `source_type` fails / the both-sources test returns 201 instead of 422).

- [ ] **Step 3: Extend the schemas + builder + validation**

In `app/api/excel_templates.py`, extend `ColumnIn`:

```python
class ColumnIn(BaseModel):
    col_letter: str
    tag_id: int | None = None
    agg: str = "avg"
    source_code: str = ""
    enabled: bool = True
    source_type: str = "tag"
    variable_id: int | None = None
    write_mode: str | None = None
    reduce_op: str | None = None
    target_mode: str = "column"
    target_cell: str | None = None
    variable_code_snapshot: str | None = None
```

`ColumnOut(ColumnIn)` already inherits the new fields. Extend `_to_out`'s `ColumnOut(...)` construction and `create_template`'s `ExcelTemplateColumn(...)` construction to pass every new field (mirror the existing field list). Add a validation helper and call it at the top of `create_template`:

```python
def _validate_columns(columns: list[ColumnIn]) -> None:
    for c in columns:
        if c.source_type == "variable":
            if c.variable_id is None or c.tag_id is not None:
                raise HTTPException(
                    422, f"{c.col_letter}: variable sütunu yalnız variable_id ister (tag_id boş)"
                )
            if c.write_mode == "series" and c.target_mode != "column":
                raise HTTPException(422, f"{c.col_letter}: write_mode=series yalnız target_mode=column ile geçerli")
            if c.target_mode == "cell" and not c.target_cell:
                raise HTTPException(422, f"{c.col_letter}: target_mode=cell için target_cell gerekir")
        elif c.variable_id is not None:
            raise HTTPException(422, f"{c.col_letter}: tag sütununda variable_id olamaz")
```

Call `_validate_columns(payload.columns)` as the first line of `create_template` (before decoding the blob).

- [ ] **Step 4: Run tests to verify they pass (incl. no regression)**

Run: `python -m pytest tests/test_excel_templates_api.py -n0`
Expected: PASS — existing tag-column tests (which omit the new fields → defaults `source_type="tag"`) stay green; 2 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/excel_templates.py \
        scada-reporter/backend/tests/test_excel_templates_api.py
git commit -m "feat(excel-binding): round-trip + validate variable-binding column fields in API"
```

---

### Task 7: Conservative unit compatibility check

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/units.py`
- Modify: `scada-reporter/backend/app/services/facility_variables/service.py` (call the check, collect warnings)
- Modify: `scada-reporter/backend/app/api/facility_variables.py` (surface warnings on create/update + validate)
- Test: `scada-reporter/backend/tests/test_facility_variable_units.py`

**Interfaces:**
- Produces:
  - `unit_warnings(db, expression) -> list[str]` (async) — walks the expression; for `add`/`sub` whose operands resolve to **different, non-empty** units (tag.unit or referenced variable.unit), returns a human warning. Conservative: unknown/empty units never warn; `mul`/`div` never warn (products legitimately change units); this is **warn-only**, never blocks the save.
  - `create_variable` / `update_variable` return value is unchanged (the variable); the warnings are computed and returned to the API separately. To avoid changing those signatures, expose a thin `unit_warnings` call from the API layer right after a successful create/update and include it in the response under a `warnings` field. (Keep the service functions pure CRUD; the API composes the warning.)

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_units.py`:

```python
import pytest

from app.models.tag import Tag
from app.services.facility_variables.units import unit_warnings


async def _tag(db, name, unit):
    t = Tag(node_id=name, name=name, unit=unit)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_add_incompatible_units_warns(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    b = await _tag(db_session, "B", "kWh/gun")
    expr = {
        "op": "add",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "agg", "source": {"type": "tag", "tag_id": b.id}, "agg": "sum", "window": "day"},
        ],
    }
    warns = await unit_warnings(db_session, expr)
    assert warns


@pytest.mark.asyncio
async def test_add_same_units_no_warn(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    b = await _tag(db_session, "B", "m3/gun")
    expr = {
        "op": "add",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "agg", "source": {"type": "tag", "tag_id": b.id}, "agg": "sum", "window": "day"},
        ],
    }
    assert await unit_warnings(db_session, expr) == []


@pytest.mark.asyncio
async def test_mul_never_warns(db_session):
    a = await _tag(db_session, "A", "m3/gun")
    expr = {
        "op": "mul",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": a.id}, "agg": "sum", "window": "day"},
            {"op": "const", "value": 3.0},
        ],
    }
    assert await unit_warnings(db_session, expr) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_units.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.units'`.

- [ ] **Step 3: Write the units checker**

Create `app/services/facility_variables/units.py`:

```python
"""Muhafazakâr birim uyumluluk uyarısı (v1: yalnız uyar, asla engelleme).

add/sub: operandların birimleri farklı ve ikisi de boş değilse uyar. mul/div
birimleri meşru biçimde değiştirir → uyarmaz. Bilinmeyen/boş birim → uyarmaz.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag


async def _leaf_unit(db: AsyncSession, node: dict) -> str | None:
    """Bir düğümün taşıdığı birim (çözülebiliyorsa). Aritmetikte ilk somut birim."""
    op = node.get("op")
    if op in ("agg", "series"):
        src = node.get("source") or {}
        if src.get("type") == "tag":
            tag = (await db.execute(select(Tag).where(Tag.id == src.get("tag_id")))).scalar_one_or_none()
            return tag.unit if tag and tag.unit else None
        return None
    if op == "ref":
        var = await db.get(FacilityVariable, node.get("variable_id"))
        return var.unit if var and var.unit else None
    if op in ("round", "abs"):
        return await _leaf_unit(db, node.get("source") or {})
    if op in ("add", "sub", "coalesce"):
        for a in node.get("args", []):
            u = await _leaf_unit(db, a)
            if u:
                return u
    return None


async def unit_warnings(db: AsyncSession, expression: dict) -> list[str]:
    warns: list[str] = []
    await _walk(db, expression, warns)
    return warns


async def _walk(db: AsyncSession, node: object, warns: list[str]) -> None:
    if not isinstance(node, dict):
        return
    op = node.get("op")
    if op in ("add", "sub"):
        units = []
        for a in node.get("args", []):
            u = await _leaf_unit(db, a)
            if u:
                units.append(u)
        distinct = set(units)
        if len(distinct) > 1:
            warns.append(f"{op}: uyumsuz birimler {sorted(distinct)} — sonuç anlamsız olabilir")
    for a in node.get("args", []):
        await _walk(db, a, warns)
    if "source" in node:
        await _walk(db, node["source"], warns)
```

- [ ] **Step 4: Surface warnings in the API create/update responses**

In `app/api/facility_variables.py`, import `unit_warnings`, add an optional `warnings: list[str] = []` field to `VariableResponse`, and populate it after a successful create/update:

```python
from app.services.facility_variables.units import unit_warnings
```

In `create` and `update`, after building `var`, compute `warns = await unit_warnings(db, body.expression)` and return `VariableResponse.of(var)` with `.warnings = warns` set (or extend `VariableResponse.of` to accept an optional `warnings` arg). Keep `VariableResponse.of`'s existing callers (list/detail) defaulting `warnings=[]`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_facility_variable_units.py tests/test_facility_variables_api.py -n0`
Expected: PASS — units tests (3); API tests still green (warnings default empty for const expressions).

- [ ] **Step 6: Run the full suite + per-file static checks**

Run: `cd scada-reporter/backend && python -m pytest -n0 -q`
Then per changed file: `python -m ruff check <files> && python -m mypy <files> && python -m ruff format --check <files> && python -m bandit -q <new files>`
Expected: all green; bandit zero on new files.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/units.py \
        scada-reporter/backend/app/services/facility_variables/service.py \
        scada-reporter/backend/app/api/facility_variables.py \
        scada-reporter/backend/tests/test_facility_variable_units.py
git commit -m "feat(facility-vars): conservative unit-compatibility warnings on add/sub"
```

---

## Self-Review

**1. Spec coverage (Plan 2 scope = Excel binding):**
- Excel binding extension fields (`source_type`, `variable_id`, `write_mode`, `reduce_op`, `target_mode`, `target_cell`, `variable_code_snapshot`) → Task 2 ✓
- Backward-compat `source_type=tag` → server defaults (Task 2) + fill dispatch (Task 4) + legacy tests stay green (Tasks 2/4/6) ✓
- Targeting rules (column vs cell; `write_mode=series` only with `target_mode=column`) → Task 6 validation + Task 3/4 behavior ✓
- Binding resolver (one shared aggregation/tz path via `evaluate_variable`) → Tasks 1/3 ✓
- Output-shape contract `{day_no: value}` consumed by unchanged fill loop → Task 4 ✓
- Dangling-binding guard (block deactivate when referenced; fill-time warning not silent blank) → Task 5 (deactivate block) + Task 3/4 (warnings) ✓
- Kind-lock-while-bound → satisfied trivially (kind immutable post-create in Plan 1; documented) ✓
- `source_code` reconciliation (kept as WinCC label; `variable_code_snapshot` is the variable label) → Task 2 field + Task 6 round-trip ✓
- Unit compatibility (conservative, warn-only) → Task 7 ✓

**Carried out of scope (later plans):** `quality_policy` leaf-read filtering + PostgreSQL cagg routing (separate perf/correctness plan; engine stays on Plan-1 raw bucketing, parity test still guards); archive `variable_refs_json` version stamping → Plan 3; advanced-reports variable selection → Plan 3; all UI (list/wizard/builder/preview/Excel-mapping/i18n) → Plan 4; seeding + workbook migration → Plan 5.

**2. Placeholder scan:** No TBD/TODO. Every code step has full code; every test step has full assertions. One cleanup note is explicit (Task 3 `_month_bounds` redundant line + possibly-unused `calendar` import — instruction says run ruff and remove).

**3. Type consistency:** `BindingResult(kind, days, scalar, warnings)` defined in Task 3, consumed in Task 4. `resolve_column(db, col, year, month, tz_offset_hours)` signature identical across Tasks 3/4. `evaluate_variable(db, var, *, start, end, grain, tz_offset_hours)` defined Task 1, consumed Tasks 3. `columns_referencing_variable` / `deactivate_variable(..., force=)` defined Task 5, used in Task 5 API. `unit_warnings(db, expression)` defined Task 7, consumed Task 7 API. New `ColumnIn` fields (Task 6) match the model fields (Task 2) one-for-one.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-29-facility-variables-excel-binding.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

**Which approach?**
