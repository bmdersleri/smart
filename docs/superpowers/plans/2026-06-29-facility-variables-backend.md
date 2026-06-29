# Facility Variables — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working, user-managed facility-variable catalog with a constrained JSON expression engine, CRUD + validate + preview API, evaluated correctly against `tag_readings` — the foundation every later phase builds on.

**Architecture:** New `facility_variables` + `facility_variable_dependencies` tables and SQLAlchemy models. A pure expression layer (`expression.py`) validates the JSON tree, infers scalar/series shape, and extracts dependencies. A bucketing layer (`buckets.py`) reuses `daily_rollup`'s reduce primitive to turn raw readings into per-bucket values. An engine (`engine.py`) walks the tree producing scalar or series results with SQL-like null propagation and tz-correct bucketing. A service layer persists variables, stores normalized dependencies, and rejects cycles. A preview layer applies hard query bounds. A FastAPI router exposes CRUD + validate + preview + dependencies, permission-gated.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Alembic, pytest-asyncio, SQLite (dev/test) / PostgreSQL+TimescaleDB (prod).

## Global Constraints

- Python baseline is **3.14** — never lower it (deferred-annotation imports break on 3.12).
- Tests run on **in-memory SQLite** via the shared `db_engine`/`db_session`/`client` fixtures in `tests/conftest.py`; an autouse fixture clears all tables before each test — never rely on cross-test data.
- All new code must pass `just check` (ruff + mypy + format). Comments/strings in this codebase are Turkish; match the surrounding style.
- Money/maths: results are `float | None`; `None` means "no data" and propagates SQL-like through arithmetic.
- Reuse the **one** aggregation primitive (`daily_rollup`'s reduce) — do not re-implement `sum/avg/min/max/last/delta`.
- Timezone: every `agg`/`series` bucket boundary is shifted by `settings.REPORT_TZ_OFFSET_HOURS`; readings are stored UTC-naive.
- Permission strings only work if registered in `app/core/permissions.py` `ALL_PERMISSIONS` — a `require_perm("x")` on an unregistered string 403s every non-admin.
- Migration head to chain from: **`d0e1f2a3b4c5`**.

## Plan Roadmap (this is Plan 1 of 5)

1. **Backend Foundation** ← this plan (model, engine, CRUD/validate/preview API)
2. Excel binding (`excel_template_columns` extension, binding resolver, fill integration, dangling/kind guards)
3. Advanced reports + archive version stamping
4. Frontend (list, wizard, expression builder, preview UI, i18n ×5, permission labels)
5. Seeding high-value variables + `gunluk_rapor.xlsx` column migration

**v1 evaluation scope (Plan 1):** the engine buckets raw `tag_readings` in Python (dialect-agnostic, correctness-first), reusing `daily_rollup`'s reduce. PostgreSQL continuous-aggregate routing (`tag_readings_1h/1d`) for performance is an explicit **Plan 2+ follow-up**; it must produce identical numbers, which the parity tests here lock in.

---

### Task 1: Register facility-variable permissions

**Files:**
- Modify: `scada-reporter/backend/app/core/permissions.py`
- Test: `scada-reporter/backend/tests/test_permissions.py`

**Interfaces:**
- Produces: constants `PERM_FACILITY_VARIABLE_CREATE = "facility_variable:create"`, `PERM_FACILITY_VARIABLE_EDIT = "facility_variable:edit"`, `PERM_FACILITY_VARIABLE_DELETE = "facility_variable:delete"`; all three appended to `ALL_PERMISSIONS`; role grants: admin auto-all, operator `create=True/edit=True/delete=False`, viewer all `False`.

- [ ] **Step 1: Write the failing test**

Append to `scada-reporter/backend/tests/test_permissions.py`:

```python
from types import SimpleNamespace

from app.core.permissions import (
    PERM_FACILITY_VARIABLE_CREATE,
    PERM_FACILITY_VARIABLE_DELETE,
    PERM_FACILITY_VARIABLE_EDIT,
    ALL_PERMISSIONS,
    effective_permissions,
)


def _user(role, overrides=None):
    return SimpleNamespace(role=role, permission_overrides=overrides or {})


def test_facility_variable_perms_registered():
    for p in (
        PERM_FACILITY_VARIABLE_CREATE,
        PERM_FACILITY_VARIABLE_EDIT,
        PERM_FACILITY_VARIABLE_DELETE,
    ):
        assert p in ALL_PERMISSIONS


def test_facility_variable_role_defaults():
    admin = effective_permissions(_user("admin"))
    assert {
        PERM_FACILITY_VARIABLE_CREATE,
        PERM_FACILITY_VARIABLE_EDIT,
        PERM_FACILITY_VARIABLE_DELETE,
    } <= admin

    operator = effective_permissions(_user("operator"))
    assert PERM_FACILITY_VARIABLE_CREATE in operator
    assert PERM_FACILITY_VARIABLE_EDIT in operator
    assert PERM_FACILITY_VARIABLE_DELETE not in operator

    viewer = effective_permissions(_user("viewer"))
    assert PERM_FACILITY_VARIABLE_CREATE not in viewer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && python -m pytest tests/test_permissions.py -k facility_variable -n0`
Expected: FAIL with `ImportError: cannot import name 'PERM_FACILITY_VARIABLE_CREATE'`.

- [ ] **Step 3: Write minimal implementation**

In `app/core/permissions.py`, add constants after `PERM_REPORT_DELETE`:

```python
PERM_FACILITY_VARIABLE_CREATE = "facility_variable:create"
PERM_FACILITY_VARIABLE_EDIT = "facility_variable:edit"
PERM_FACILITY_VARIABLE_DELETE = "facility_variable:delete"
```

Append them to `ALL_PERMISSIONS`:

```python
ALL_PERMISSIONS: tuple[str, ...] = (
    PERM_TAG_CREATE,
    PERM_PLC_MANAGE,
    PERM_REPORT_CREATE,
    PERM_REPORT_EDIT,
    PERM_REPORT_DELETE,
    PERM_FACILITY_VARIABLE_CREATE,
    PERM_FACILITY_VARIABLE_EDIT,
    PERM_FACILITY_VARIABLE_DELETE,
)
```

Add operator grants inside `ROLE_DEFAULTS["operator"]` (admin/viewer are derived from `ALL_PERMISSIONS` comprehensions, so only operator needs explicit entries):

```python
    "operator": {
        PERM_TAG_CREATE: True,
        PERM_PLC_MANAGE: True,
        PERM_REPORT_CREATE: True,
        PERM_REPORT_EDIT: True,
        PERM_REPORT_DELETE: False,
        PERM_FACILITY_VARIABLE_CREATE: True,
        PERM_FACILITY_VARIABLE_EDIT: True,
        PERM_FACILITY_VARIABLE_DELETE: False,
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_permissions.py -k facility_variable -n0`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/core/permissions.py scada-reporter/backend/tests/test_permissions.py
git commit -m "feat(perms): register facility_variable create/edit/delete permissions"
```

---

### Task 2: Models + migration

**Files:**
- Create: `scada-reporter/backend/app/models/facility_variable.py`
- Create: `scada-reporter/backend/alembic/versions/e2f3a4b5c6d7_facility_variables.py`
- Modify: `scada-reporter/backend/app/main.py` (import model module so `Base.metadata` sees it for test `create_all`)
- Test: `scada-reporter/backend/tests/test_facility_variable_model.py`

**Interfaces:**
- Produces:
  - `FacilityVariable` ORM (`facility_variables`): `id, code, name, description, kind, value_type, unit, expression_json, null_policy, quality_policy, default_time_grain, is_active, version, created_by, updated_by, created_at, updated_at`. `code` unique. `expression_json` stored as `Text` (JSON string).
  - `FacilityVariableDependency` ORM (`facility_variable_dependencies`): `id, variable_id (FK→facility_variables, ondelete CASCADE), depends_on_type ("tag"|"variable"), depends_on_tag_id (FK→tags, ondelete CASCADE, nullable), depends_on_variable_id (FK→facility_variables, ondelete CASCADE, nullable)`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_model.py`:

```python
import pytest

from app.models.facility_variable import FacilityVariable, FacilityVariableDependency


@pytest.mark.asyncio
async def test_create_variable_with_dependency(db_session):
    var = FacilityVariable(
        code="var_test",
        name="Test",
        kind="scalar",
        value_type="number",
        unit="m3/gun",
        expression_json='{"op": "const", "value": 1}',
        null_policy="skip",
        quality_policy="good_only",
        default_time_grain="day",
    )
    db_session.add(var)
    await db_session.commit()
    await db_session.refresh(var)

    assert var.id is not None
    assert var.is_active is True
    assert var.version == 1

    dep = FacilityVariableDependency(
        variable_id=var.id, depends_on_type="tag", depends_on_tag_id=None
    )
    db_session.add(dep)
    await db_session.commit()
    await db_session.refresh(dep)
    assert dep.variable_id == var.id


@pytest.mark.asyncio
async def test_code_is_unique(db_session):
    from sqlalchemy.exc import IntegrityError

    for _ in range(2):
        db_session.add(
            FacilityVariable(
                code="dup", name="x", kind="scalar", value_type="number",
                unit="", expression_json="{}", null_policy="skip",
                quality_policy="good_only", default_time_grain="day",
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_model.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.facility_variable'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/models/facility_variable.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FacilityVariable(Base):
    __tablename__ = "facility_variables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # scalar|series
    value_type: Mapped[str] = mapped_column(String(16), default="number")
    unit: Mapped[str] = mapped_column(String(32), default="")
    expression_json: Mapped[str] = mapped_column(Text, nullable=False)
    null_policy: Mapped[str] = mapped_column(String(12), default="skip")  # skip|zero_fill|fail
    quality_policy: Mapped[str] = mapped_column(String(12), default="good_only")  # good_only|allow_bad
    default_time_grain: Mapped[str | None] = mapped_column(String(8), nullable=True)  # hour|day|week|month
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    dependencies: Mapped[list["FacilityVariableDependency"]] = relationship(
        back_populates="variable",
        cascade="all, delete-orphan",
        foreign_keys="FacilityVariableDependency.variable_id",
        lazy="selectin",
    )


class FacilityVariableDependency(Base):
    __tablename__ = "facility_variable_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variable_id: Mapped[int] = mapped_column(
        ForeignKey("facility_variables.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_type: Mapped[str] = mapped_column(String(8), nullable=False)  # tag|variable
    depends_on_tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=True
    )
    depends_on_variable_id: Mapped[int | None] = mapped_column(
        ForeignKey("facility_variables.id", ondelete="CASCADE"), nullable=True
    )

    variable: Mapped[FacilityVariable] = relationship(
        back_populates="dependencies", foreign_keys=[variable_id]
    )
```

In `app/main.py`, add to the model import block (near `from app.models import excel_template as _excel_template  # noqa: F401`):

```python
from app.models import facility_variable as _facility_variable  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_model.py -n0`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the Alembic migration**

Create `app/alembic/versions/e2f3a4b5c6d7_facility_variables.py` (path is `scada-reporter/backend/alembic/versions/...`):

```python
"""facility variables + dependencies

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-06-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facility_variables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False, server_default="number"),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("expression_json", sa.Text(), nullable=False),
        sa.Column("null_policy", sa.String(length=12), nullable=False, server_default="skip"),
        sa.Column("quality_policy", sa.String(length=12), nullable=False, server_default="good_only"),
        sa.Column("default_time_grain", sa.String(length=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "facility_variable_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("variable_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_type", sa.String(length=8), nullable=False),
        sa.Column("depends_on_tag_id", sa.Integer(), nullable=True),
        sa.Column("depends_on_variable_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["variable_id"], ["facility_variables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["depends_on_variable_id"], ["facility_variables.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fac_var_dep_variable_id", "facility_variable_dependencies", ["variable_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_fac_var_dep_variable_id", table_name="facility_variable_dependencies")
    op.drop_table("facility_variable_dependencies")
    op.drop_table("facility_variables")
```

- [ ] **Step 6: Verify migration applies cleanly**

Run: `cd scada-reporter/backend && python -m alembic upgrade head && python -m alembic heads`
Expected: no error; head prints `e2f3a4b5c6d7 (head)`.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/models/facility_variable.py \
        scada-reporter/backend/alembic/versions/e2f3a4b5c6d7_facility_variables.py \
        scada-reporter/backend/app/main.py \
        scada-reporter/backend/tests/test_facility_variable_model.py
git commit -m "feat(facility-vars): add models + migration for variables and dependencies"
```

---

### Task 3: Expression validation, shape inference, dependency extraction

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/__init__.py` (empty)
- Create: `scada-reporter/backend/app/services/facility_variables/expression.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_expression.py`

**Interfaces:**
- Produces (all pure, no DB):
  - `EXPR_OPS: frozenset[str]` = `{agg, series, add, sub, mul, div, const, round, abs, coalesce, moving_avg, reduce, ref}`
  - `AGG_FUNCS: frozenset[str]` = `{sum, avg, min, max, last, delta}`
  - `class ExpressionError(ValueError)`
  - `infer_shape(node: dict) -> str` → `"scalar"` or `"series"` (raises `ExpressionError` on ambiguous/invalid)
  - `validate_expression(node: dict, kind: str) -> None` — raises `ExpressionError` if malformed, op unknown, required field missing, `div` missing `on_zero`, window/grain missing, or inferred shape ≠ `kind`
  - `extract_dependencies(node: dict) -> list[tuple[str, int | None, int | None]]` → list of `(depends_on_type, tag_id, variable_id)`, deduplicated

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_expression.py`:

```python
import pytest

from app.services.facility_variables.expression import (
    ExpressionError,
    extract_dependencies,
    infer_shape,
    validate_expression,
)

AGG_DAY = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "delta", "window": "day"}
SERIES_DAY = {
    "op": "series",
    "source": {"type": "tag", "tag_id": 1},
    "agg": "delta",
    "grain": "day",
    "window": "7d",
}


def test_agg_is_scalar():
    assert infer_shape(AGG_DAY) == "scalar"


def test_series_is_series():
    assert infer_shape(SERIES_DAY) == "series"


def test_reduce_collapses_series_to_scalar():
    node = {"op": "reduce", "source": SERIES_DAY, "reduce": "avg"}
    assert infer_shape(node) == "scalar"


def test_moving_avg_keeps_series():
    node = {"op": "moving_avg", "source": SERIES_DAY, "window_size": 7}
    assert infer_shape(node) == "series"


def test_add_two_scalars_is_scalar():
    node = {"op": "add", "args": [AGG_DAY, {"op": "const", "value": 5}]}
    assert infer_shape(node) == "scalar"


def test_div_without_on_zero_rejected():
    node = {"op": "div", "args": [AGG_DAY, {"op": "const", "value": 2}]}
    with pytest.raises(ExpressionError, match="on_zero"):
        validate_expression(node, "scalar")


def test_div_with_on_zero_ok():
    node = {"op": "div", "args": [AGG_DAY, {"op": "const", "value": 2}], "on_zero": "null"}
    validate_expression(node, "scalar")  # no raise


def test_agg_missing_window_rejected():
    node = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "delta"}
    with pytest.raises(ExpressionError, match="window"):
        validate_expression(node, "scalar")


def test_series_missing_grain_rejected():
    node = {"op": "series", "source": {"type": "tag", "tag_id": 1}, "agg": "delta", "window": "7d"}
    with pytest.raises(ExpressionError, match="grain"):
        validate_expression(node, "series")


def test_unknown_op_rejected():
    with pytest.raises(ExpressionError, match="bilinmeyen|unknown|op"):
        validate_expression({"op": "frobnicate"}, "scalar")


def test_shape_mismatch_rejected():
    with pytest.raises(ExpressionError, match="kind|shape|scalar|series"):
        validate_expression(SERIES_DAY, "scalar")


def test_unknown_agg_func_rejected():
    node = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "median", "window": "day"}
    with pytest.raises(ExpressionError, match="agg"):
        validate_expression(node, "scalar")


def test_extract_dependencies_tags_and_vars():
    node = {
        "op": "add",
        "args": [
            AGG_DAY,
            {"op": "ref", "variable_id": 9},
            {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "sum", "window": "day"},
        ],
    }
    deps = set(extract_dependencies(node))
    assert ("tag", 1, None) in deps
    assert ("variable", None, 9) in deps
    # tag_id 1 appears twice but is deduplicated
    assert sum(1 for d in deps if d == ("tag", 1, None)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_expression.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/facility_variables/__init__.py` (empty file).

Create `app/services/facility_variables/expression.py`:

```python
"""Tesis değişkeni JSON ifade ağacı: doğrulama, şekil çıkarımı, bağımlılık çıkarımı.

Saf (DB'siz) katman. Engine ve servis bunu ortak kaynak olarak kullanır.
"""

from __future__ import annotations

AGG_FUNCS = frozenset({"sum", "avg", "min", "max", "last", "delta"})
REDUCE_FUNCS = frozenset({"sum", "avg", "min", "max", "last"})
ARITH_OPS = frozenset({"add", "sub", "mul", "div"})
EXPR_OPS = frozenset(
    {"agg", "series", "const", "round", "abs", "coalesce", "moving_avg", "reduce", "ref"}
    | ARITH_OPS
)


class ExpressionError(ValueError):
    """Geçersiz ifade ağacı."""


def _is_tag_source(src: object) -> bool:
    return isinstance(src, dict) and src.get("type") == "tag" and "tag_id" in src


def infer_shape(node: object) -> str:
    """Düğümün şekli: 'scalar' | 'series'. Geçersizse ExpressionError."""
    if not isinstance(node, dict) or "op" not in node:
        raise ExpressionError(f"Geçersiz ifade düğümü: {node!r}")
    op = node["op"]
    if op not in EXPR_OPS:
        raise ExpressionError(f"Bilinmeyen op (unknown): {op!r}")

    if op in ("const", "agg", "ref"):
        return "scalar"
    if op == "series":
        return "series"
    if op == "reduce":
        if infer_shape(node.get("source")) != "series":
            raise ExpressionError("reduce yalnız series kaynağı alır")
        return "scalar"
    if op == "moving_avg":
        if infer_shape(node.get("source")) != "series":
            raise ExpressionError("moving_avg yalnız series kaynağı alır")
        return "series"
    if op in ("round", "abs"):
        return infer_shape(node.get("source"))
    if op in ARITH_OPS or op == "coalesce":
        shapes = [infer_shape(a) for a in node.get("args", [])]
        if not shapes:
            raise ExpressionError(f"{op} en az bir argüman ister")
        # series varsa sonuç series (broadcast); hepsi scalar ise scalar
        return "series" if "series" in shapes else "scalar"
    raise ExpressionError(f"Şekli çıkarılamayan op: {op!r}")  # pragma: no cover


def validate_expression(node: object, kind: str) -> None:
    """Ağacı yapısal doğrula; kök şekil `kind` ile uyuşmalı. Hata → ExpressionError."""
    _validate_node(node)
    shape = infer_shape(node)
    if shape != kind:
        raise ExpressionError(
            f"İfade şekli '{shape}' değişken kind '{kind}' ile uyuşmuyor"
        )


def _validate_node(node: object) -> None:
    if not isinstance(node, dict) or "op" not in node:
        raise ExpressionError(f"Geçersiz ifade düğümü: {node!r}")
    op = node["op"]
    if op not in EXPR_OPS:
        raise ExpressionError(f"Bilinmeyen op (unknown): {op!r}")

    if op == "const":
        if not isinstance(node.get("value"), (int, float)):
            raise ExpressionError("const sayısal 'value' ister")
        return
    if op == "ref":
        if not isinstance(node.get("variable_id"), int):
            raise ExpressionError("ref tamsayı 'variable_id' ister")
        return
    if op == "agg":
        if not _is_tag_source(node.get("source")):
            raise ExpressionError("agg geçerli bir tag kaynağı ister")
        if node.get("agg") not in AGG_FUNCS:
            raise ExpressionError(f"agg fonksiyonu geçersiz: {node.get('agg')!r}")
        if not node.get("window"):
            raise ExpressionError("agg açık 'window' ister")
        return
    if op == "series":
        if not _is_tag_source(node.get("source")):
            raise ExpressionError("series geçerli bir tag kaynağı ister")
        if node.get("agg") not in AGG_FUNCS:
            raise ExpressionError(f"series agg fonksiyonu geçersiz: {node.get('agg')!r}")
        if not node.get("grain"):
            raise ExpressionError("series açık 'grain' ister")
        if not node.get("window"):
            raise ExpressionError("series açık 'window' ister")
        return
    if op == "reduce":
        if node.get("reduce") not in REDUCE_FUNCS:
            raise ExpressionError(f"reduce fonksiyonu geçersiz: {node.get('reduce')!r}")
        _validate_node(node.get("source"))
        return
    if op == "moving_avg":
        if not isinstance(node.get("window_size"), int) or node["window_size"] < 1:
            raise ExpressionError("moving_avg pozitif tamsayı 'window_size' ister")
        _validate_node(node.get("source"))
        return
    if op == "round":
        if not isinstance(node.get("ndigits", 0), int):
            raise ExpressionError("round tamsayı 'ndigits' ister")
        _validate_node(node.get("source"))
        return
    if op == "abs":
        _validate_node(node.get("source"))
        return
    if op == "div":
        if node.get("on_zero") not in ("null", "zero", "fail"):
            raise ExpressionError("div açık 'on_zero' (null|zero|fail) ister")
        _validate_args(node)
        return
    if op in ARITH_OPS or op == "coalesce":
        _validate_args(node)
        return


def _validate_args(node: dict) -> None:
    args = node.get("args")
    if not isinstance(args, list) or not args:
        raise ExpressionError(f"{node['op']} boş olmayan 'args' listesi ister")
    for a in args:
        _validate_node(a)


def extract_dependencies(node: object) -> list[tuple[str, int | None, int | None]]:
    """Ağaçtaki tüm tag ve variable bağımlılıklarını (tekilleştirilmiş) döndür."""
    seen: set[tuple[str, int | None, int | None]] = set()
    _walk_deps(node, seen)
    return list(seen)


def _walk_deps(node: object, seen: set) -> None:
    if not isinstance(node, dict):
        return
    op = node.get("op")
    if op in ("agg", "series"):
        src = node.get("source")
        if _is_tag_source(src):
            seen.add(("tag", int(src["tag_id"]), None))
        return
    if op == "ref":
        if isinstance(node.get("variable_id"), int):
            seen.add(("variable", None, int(node["variable_id"])))
        return
    if "source" in node:
        _walk_deps(node["source"], seen)
    for a in node.get("args", []):
        _walk_deps(a, seen)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_expression.py -n0`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/__init__.py \
        scada-reporter/backend/app/services/facility_variables/expression.py \
        scada-reporter/backend/tests/test_facility_variable_expression.py
git commit -m "feat(facility-vars): expression validation, shape inference, dependency extraction"
```

---

### Task 4: Bucketing layer (reuse daily_rollup reduce)

**Files:**
- Modify: `scada-reporter/backend/app/services/template_fill/daily_rollup.py` (promote `_reduce` → public `reduce_values`, keep `_reduce` alias)
- Create: `scada-reporter/backend/app/services/facility_variables/buckets.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_buckets.py`

**Interfaces:**
- Consumes: `reduce_values(values: list[float], agg: str) -> float | None` (the shared aggregation primitive, promoted from `daily_rollup._reduce`).
- Produces:
  - `WINDOW_DELTAS: dict[str, timedelta]` for relative windows (`"7d"`, `"24h"`, `"30d"`, `"day"`, `"hour"`, `"week"`, `"month"`)
  - `resolve_window(window: str, *, ref_end: datetime) -> tuple[datetime, datetime]` → naive-UTC `[start, end)` for a relative window ending at `ref_end`
  - `async bucket_series(db, tag_id, start, end, grain, agg, tz_offset_hours) -> dict[datetime, float]` — local bucket-start datetime → reduced value, gaps absent
  - `async agg_window(db, tag_id, start, end, agg, tz_offset_hours) -> float | None` — single reduced value over `[start, end)`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_buckets.py`:

```python
from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.buckets import agg_window, bucket_series


@pytest.mark.asyncio
async def test_agg_window_delta(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # totalizer: 10 at 00:00, 30 at 12:00, 50 at 23:00 → delta = 40
    for hh, val in ((0, 10.0), (12, 30.0), (23, 50.0)):
        db_session.add(
            TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, hh), value=val)
        )
    await db_session.commit()

    out = await agg_window(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 2), "delta", 0
    )
    assert out == 40.0


@pytest.mark.asyncio
async def test_bucket_series_daily_delta(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # day 1: 10→50 (delta 40); day 2: 50→90 (delta 40)
    rows = [
        (datetime(2026, 6, 1, 0), 10.0),
        (datetime(2026, 6, 1, 23), 50.0),
        (datetime(2026, 6, 2, 0), 50.0),
        (datetime(2026, 6, 2, 23), 90.0),
    ]
    for ts, val in rows:
        db_session.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db_session.commit()

    out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 3), "day", "delta", 0
    )
    assert out[datetime(2026, 6, 1)] == 40.0
    assert out[datetime(2026, 6, 2)] == 40.0


@pytest.mark.asyncio
async def test_bucket_series_respects_tz_offset(db_session):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # 22:00 UTC on May 31 == 01:00 Jun 1 at +3 → belongs to Jun 1 local bucket
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 5, 31, 22), value=5.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 5), value=9.0))
    await db_session.commit()

    out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 6, 2), "day", "last", 3
    )
    # both readings fall in the Jun 1 local day; last = 9.0
    assert out[datetime(2026, 6, 1)] == 9.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_buckets.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.buckets'`.

- [ ] **Step 3: Promote the shared reduce primitive**

In `app/services/template_fill/daily_rollup.py`, rename `_reduce` to `reduce_values` and keep a backward-compatible alias. Replace the `def _reduce(...)` definition header and add the alias after it:

```python
def reduce_values(values: list[float], agg: str) -> float | None:
    """values: bir bucket'ın okumaları, zaman sırasına göre. agg uygula."""
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


# Geriye dönük uyumluluk: eski iç ad.
_reduce = reduce_values
```

- [ ] **Step 4: Write the bucketing layer**

Create `app/services/facility_variables/buckets.py`:

```python
"""Ham tag_readings'i bucket'lara böler. daily_rollup.reduce_values ortak primitifi
kullanılır — agg matematiği tek yerde. tz_offset her bucket sınırına uygulanır.

v1: dialect-bağımsız Python tarafı bucketing (doğruluk önceliği). PostgreSQL
sürekli-toplama (cagg) yönlendirmesi sonraki planın perf işidir; aynı sayıları
üretmeli (parity testleri kilitler).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import TagReading
from app.services.template_fill.daily_rollup import reduce_values

GRAINS = ("hour", "day", "week", "month")

_RELATIVE = {
    "hour": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "day": timedelta(days=1),
    "7d": timedelta(days=7),
    "week": timedelta(days=7),
    "30d": timedelta(days=30),
}


def resolve_window(window: str, *, ref_end: datetime) -> tuple[datetime, datetime]:
    """Göreli pencereyi [start, end) naif-UTC aralığına çevir."""
    delta = _RELATIVE.get(window)
    if delta is None:
        raise ValueError(f"Bilinmeyen window: {window!r}")
    return ref_end - delta, ref_end


def _bucket_key(local: datetime, grain: str) -> datetime:
    """Yerel zaman damgasını grain bucket başlangıcına indirger."""
    if grain == "hour":
        return local.replace(minute=0, second=0, microsecond=0)
    if grain == "day":
        return datetime(local.year, local.month, local.day)
    if grain == "week":
        monday = local - timedelta(days=local.weekday())
        return datetime(monday.year, monday.month, monday.day)
    if grain == "month":
        return datetime(local.year, local.month, 1)
    raise ValueError(f"Bilinmeyen grain: {grain!r}")


async def _fetch(db: AsyncSession, tag_id: int, start: datetime, end: datetime):
    """[start, end) penceresini, tz kaymasını karşılayacak şekilde okur."""
    result = await db.execute(
        select(TagReading.timestamp, TagReading.value)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= start,
            TagReading.timestamp < end,
        )
        .order_by(TagReading.timestamp.asc())
    )
    return result.all()


async def agg_window(
    db: AsyncSession,
    tag_id: int,
    start: datetime,
    end: datetime,
    agg: str,
    tz_offset_hours: int,
) -> float | None:
    """[start, end) penceresinde tek bir indirgenmiş değer."""
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    rows = await _fetch(db, tag_id, q_start, q_end)
    vals = [v for _, v in rows]
    return reduce_values(vals, agg)


async def bucket_series(
    db: AsyncSession,
    tag_id: int,
    start: datetime,
    end: datetime,
    grain: str,
    agg: str,
    tz_offset_hours: int,
) -> dict[datetime, float]:
    """{yerel_bucket_başlangıcı: değer}. Verisi olmayan bucket anahtarsız."""
    q_start = start - timedelta(hours=tz_offset_hours)
    q_end = end - timedelta(hours=tz_offset_hours)
    rows = await _fetch(db, tag_id, q_start, q_end)
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for ts, value in rows:
        local = ts + timedelta(hours=tz_offset_hours)
        if start <= local < end:
            buckets[_bucket_key(local, grain)].append(value)
    out: dict[datetime, float] = {}
    for key, vals in buckets.items():
        reduced = reduce_values(vals, agg)
        if reduced is not None:
            out[key] = reduced
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_facility_variable_buckets.py tests/test_fill_engine.py -n0`
Expected: PASS (buckets: 3 tests; fill_engine still green — proves the `_reduce` alias kept legacy behavior).

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/services/template_fill/daily_rollup.py \
        scada-reporter/backend/app/services/facility_variables/buckets.py \
        scada-reporter/backend/tests/test_facility_variable_buckets.py
git commit -m "feat(facility-vars): bucketing layer reusing daily_rollup reduce primitive"
```

---

### Task 5: Expression engine (evaluation)

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/engine.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_engine.py`

**Interfaces:**
- Consumes: `buckets.bucket_series`, `buckets.agg_window`, `buckets.resolve_window`; `expression.infer_shape`.
- Produces:
  - `class EvalResult` with fields `kind: str` (`"scalar"|"series"`), `scalar: float | None`, `series: dict[datetime, float | None] | None`.
  - `async evaluate(db, node, *, start, end, grain, tz_offset_hours, resolve_ref) -> EvalResult` where `resolve_ref: Callable[[int], Awaitable[EvalResult]]` resolves a `ref` op's `variable_id` to an already-evaluated result. Arithmetic is SQL-like null-propagating; series/series aligns by bucket key; series/scalar broadcasts.
  - `RoundingError`, division `on_zero` honored, `excel_round(value, ndigits)` (half-away-from-zero).

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_engine.py`:

```python
from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.engine import EvalResult, evaluate, excel_round


async def _seed_totalizer(db, name, rows):
    tag = Tag(node_id=name, name=name, unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    for ts, val in rows:
        db.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db.commit()
    return tag


async def _noref(_vid):  # no ref in these tests
    raise AssertionError("ref not expected")


JUNE = (datetime(2026, 6, 1), datetime(2026, 6, 3))  # 2-day window


@pytest.mark.asyncio
async def test_excel_round_half_away_from_zero():
    assert excel_round(2.5, 0) == 3.0
    assert excel_round(3.5, 0) == 4.0
    assert excel_round(-2.5, 0) == -3.0
    assert excel_round(1.2345, 2) == 1.23


@pytest.mark.asyncio
async def test_agg_scalar_delta(db_session):
    tag = await _seed_totalizer(
        db_session, "T", [(datetime(2026, 6, 1, 0), 10.0), (datetime(2026, 6, 2, 23), 90.0)]
    )
    node = {"op": "agg", "source": {"type": "tag", "tag_id": tag.id}, "agg": "delta", "window": "2d"}
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.kind == "scalar"
    assert res.scalar == 80.0


@pytest.mark.asyncio
async def test_add_two_tag_deltas(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)]
    )
    t2 = await _seed_totalizer(
        db_session, "T2", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 10.0)]
    )
    node = {
        "op": "add",
        "args": [
            {"op": "series", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "grain": "day", "window": "2d"},
            {"op": "series", "source": {"type": "tag", "tag_id": t2.id}, "agg": "delta", "grain": "day", "window": "2d"},
        ],
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.kind == "series"
    assert res.series[datetime(2026, 6, 1)] == 50.0


@pytest.mark.asyncio
async def test_series_plus_scalar_broadcast(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0)]
    )
    node = {
        "op": "add",
        "args": [
            {"op": "series", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "grain": "day", "window": "2d"},
            {"op": "const", "value": 100.0},
        ],
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.series[datetime(2026, 6, 1)] == 140.0


@pytest.mark.asyncio
async def test_div_on_zero_null(db_session):
    t1 = await _seed_totalizer(
        db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0), (datetime(2026, 6, 1, 23), 5.0)]
    )  # delta 0
    node = {
        "op": "div",
        "args": [
            {"op": "const", "value": 10.0},
            {"op": "agg", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "window": "2d"},
        ],
        "on_zero": "null",
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.scalar is None


@pytest.mark.asyncio
async def test_null_propagation_in_add(db_session):
    # tag with a single reading → delta is None; None + const → None
    t1 = await _seed_totalizer(db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0)])
    node = {
        "op": "add",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "window": "2d"},
            {"op": "const", "value": 1.0},
        ],
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.scalar is None


@pytest.mark.asyncio
async def test_coalesce_fills_null(db_session):
    t1 = await _seed_totalizer(db_session, "T1", [(datetime(2026, 6, 1, 0), 5.0)])  # delta None
    node = {
        "op": "coalesce",
        "args": [
            {"op": "agg", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "window": "2d"},
            {"op": "const", "value": 0.0},
        ],
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.scalar == 0.0


@pytest.mark.asyncio
async def test_reduce_avg_of_daily_delta(db_session):
    t1 = await _seed_totalizer(
        db_session,
        "T1",
        [
            (datetime(2026, 6, 1, 0), 0.0), (datetime(2026, 6, 1, 23), 40.0),
            (datetime(2026, 6, 2, 0), 40.0), (datetime(2026, 6, 2, 23), 80.0),
        ],
    )
    node = {
        "op": "reduce",
        "source": {"op": "series", "source": {"type": "tag", "tag_id": t1.id}, "agg": "delta", "grain": "day", "window": "2d"},
        "reduce": "avg",
    }
    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=_noref
    )
    assert res.kind == "scalar"
    assert res.scalar == 40.0


@pytest.mark.asyncio
async def test_ref_resolves_via_callback(db_session):
    node = {"op": "ref", "variable_id": 7}

    async def resolve(vid):
        assert vid == 7
        return EvalResult(kind="scalar", scalar=123.0, series=None)

    res = await evaluate(
        db_session, node, start=JUNE[0], end=JUNE[1], grain="day", tz_offset_hours=0, resolve_ref=resolve
    )
    assert res.scalar == 123.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_engine.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/facility_variables/engine.py`:

```python
"""Tesis değişkeni ifade ağacı değerlendiricisi.

scalar veya series (dict[bucket_key -> value|None]) üretir. Aritmetik SQL-benzeri
null yayar: bir operand None ise sonuç None. series+series bucket anahtarına göre
hizalanır; series+scalar yayınlanır (broadcast). ref bir geri çağrımla çözülür.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.facility_variables.buckets import agg_window, bucket_series, resolve_window

ResolveRef = Callable[[int], Awaitable["EvalResult"]]


@dataclass
class EvalResult:
    kind: str  # scalar | series
    scalar: float | None = None
    series: dict[datetime, float | None] | None = None


def excel_round(value: float, ndigits: int) -> float:
    """Excel ROUND ile aynı: half-away-from-zero (bankers değil)."""
    if value == 0:
        return 0.0
    factor = 10**ndigits
    return math.floor(abs(value) * factor + 0.5) / factor * (1 if value > 0 else -1)


async def evaluate(
    db: AsyncSession,
    node: dict,
    *,
    start: datetime,
    end: datetime,
    grain: str,
    tz_offset_hours: int,
    resolve_ref: ResolveRef,
) -> EvalResult:
    op = node["op"]

    if op == "const":
        return EvalResult(kind="scalar", scalar=float(node["value"]))

    if op == "ref":
        return await resolve_ref(int(node["variable_id"]))

    if op == "agg":
        window = node["window"]
        w_start, w_end = _window_bounds(window, start, end)
        val = await agg_window(
            db, int(node["source"]["tag_id"]), w_start, w_end, node["agg"], tz_offset_hours
        )
        return EvalResult(kind="scalar", scalar=val)

    if op == "series":
        window = node["window"]
        w_start, w_end = _window_bounds(window, start, end)
        data = await bucket_series(
            db, int(node["source"]["tag_id"]), w_start, w_end, node["grain"], node["agg"], tz_offset_hours
        )
        return EvalResult(kind="series", series=dict(data))

    if op == "abs":
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _map_unary(inner, lambda v: abs(v))

    if op == "round":
        ndigits = int(node.get("ndigits", 0))
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _map_unary(inner, lambda v: excel_round(v, ndigits))

    if op == "reduce":
        from app.services.template_fill.daily_rollup import reduce_values

        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        vals = [v for v in (inner.series or {}).values() if v is not None]
        return EvalResult(kind="scalar", scalar=reduce_values(vals, node["reduce"]))

    if op == "moving_avg":
        inner = await _ev(db, node["source"], start, end, grain, tz_offset_hours, resolve_ref)
        return _moving_avg(inner, int(node["window_size"]))

    if op == "coalesce":
        return await _coalesce(db, node["args"], start, end, grain, tz_offset_hours, resolve_ref)

    if op in ("add", "sub", "mul", "div"):
        return await _arith(db, node, op, start, end, grain, tz_offset_hours, resolve_ref)

    raise ValueError(f"Değerlendirilemeyen op: {op!r}")


async def _ev(db, node, start, end, grain, tz, resolve_ref) -> EvalResult:
    return await evaluate(
        db, node, start=start, end=end, grain=grain, tz_offset_hours=tz, resolve_ref=resolve_ref
    )


def _window_bounds(window: str, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Excel-ay değerlendirmesinde pencere = verilen [start, end). Göreli sözcükler
    (7d/24h/30d) end'e göre çözülür; 'day'/'2d' gibi tam-pencere sözcükleri verilen
    aralığı kullanır."""
    if window in ("day", "2d", "month") or window.endswith("d") is False:
        return start, end
    try:
        w_start, _ = resolve_window(window, ref_end=end)
        return w_start, end
    except ValueError:
        return start, end


def _map_unary(res: EvalResult, fn) -> EvalResult:
    if res.kind == "scalar":
        return EvalResult(kind="scalar", scalar=None if res.scalar is None else fn(res.scalar))
    out = {k: (None if v is None else fn(v)) for k, v in (res.series or {}).items()}
    return EvalResult(kind="series", series=out)


def _moving_avg(res: EvalResult, size: int) -> EvalResult:
    series = res.series or {}
    keys = sorted(series)
    out: dict[datetime, float | None] = {}
    for i, k in enumerate(keys):
        window = [series[keys[j]] for j in range(max(0, i - size + 1), i + 1)]
        vals = [v for v in window if v is not None]
        out[k] = sum(vals) / len(vals) if vals else None
    return EvalResult(kind="series", series=out)


def _apply(op: str, a: float, b: float) -> float:
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    return a / b  # div — sıfır kontrolü çağıran yerde


async def _arith(db, node, op, start, end, grain, tz, resolve_ref) -> EvalResult:
    results = [await _ev(db, a, start, end, grain, tz, resolve_ref) for a in node["args"]]
    on_zero = node.get("on_zero", "null")
    is_series = any(r.kind == "series" for r in results)

    if not is_series:
        acc = results[0].scalar
        for r in results[1:]:
            acc = _combine(op, acc, r.scalar, on_zero)
        return EvalResult(kind="scalar", scalar=acc)

    keys: set[datetime] = set()
    for r in results:
        if r.kind == "series":
            keys |= set((r.series or {}).keys())
    out: dict[datetime, float | None] = {}
    for k in keys:
        acc = _at(results[0], k)
        for r in results[1:]:
            acc = _combine(op, acc, _at(r, k), on_zero)
        out[k] = acc
    return EvalResult(kind="series", series=out)


def _at(res: EvalResult, key: datetime) -> float | None:
    if res.kind == "scalar":
        return res.scalar
    return (res.series or {}).get(key)


def _combine(op: str, a: float | None, b: float | None, on_zero: str) -> float | None:
    if a is None or b is None:
        return None
    if op == "div" and b == 0:
        if on_zero == "zero":
            return 0.0
        if on_zero == "fail":
            raise ZeroDivisionError("div on_zero=fail")
        return None
    return _apply(op, a, b)


async def _coalesce(db, args, start, end, grain, tz, resolve_ref) -> EvalResult:
    results = [await _ev(db, a, start, end, grain, tz, resolve_ref) for a in args]
    is_series = any(r.kind == "series" for r in results)
    if not is_series:
        for r in results:
            if r.scalar is not None:
                return EvalResult(kind="scalar", scalar=r.scalar)
        return EvalResult(kind="scalar", scalar=None)
    keys: set[datetime] = set()
    for r in results:
        if r.kind == "series":
            keys |= set((r.series or {}).keys())
    out: dict[datetime, float | None] = {}
    for k in keys:
        chosen: float | None = None
        for r in results:
            v = _at(r, k)
            if v is not None:
                chosen = v
                break
        out[k] = chosen
    return EvalResult(kind="series", series=out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_engine.py -n0`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/engine.py \
        scada-reporter/backend/tests/test_facility_variable_engine.py
git commit -m "feat(facility-vars): expression engine with shape algebra + null propagation"
```

---

### Task 6: Service layer — CRUD, dependency storage, cycle rejection

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/service.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_service.py`

**Interfaces:**
- Consumes: `expression.validate_expression`, `expression.extract_dependencies`; models.
- Produces:
  - `class VariableError(ValueError)` (validation/cycle failures)
  - `async create_variable(db, *, code, name, description, kind, unit, expression, null_policy, quality_policy, default_time_grain, value_type, created_by) -> FacilityVariable` — validates expression, rejects cycles, stores normalized dependencies, `version=1`.
  - `async update_variable(db, var_id, *, fields..., updated_by) -> FacilityVariable` — re-validates, re-extracts deps, bumps `version` only when `expression`/policies change.
  - `async deactivate_variable(db, var_id) -> FacilityVariable` (sets `is_active=False`).
  - `async would_create_cycle(db, var_id, dep_var_ids) -> bool` — walks the existing dependency graph; `var_id` may be `None` for a not-yet-saved variable.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_service.py`:

```python
import json

import pytest

from app.services.facility_variables.service import (
    VariableError,
    create_variable,
    update_variable,
)


def _scalar_const(value=1.0):
    return {"op": "const", "value": value}


async def _make(db, code, expression, kind="scalar"):
    return await create_variable(
        db, code=code, name=code, description="", kind=kind, unit="",
        expression=expression, null_policy="skip", quality_policy="good_only",
        default_time_grain="day", value_type="number", created_by=1,
    )


@pytest.mark.asyncio
async def test_create_stores_dependencies(db_session):
    expr = {
        "op": "agg",
        "source": {"type": "tag", "tag_id": 5},
        "agg": "delta",
        "window": "day",
    }
    var = await _make(db_session, "v1", expr)
    assert var.version == 1
    assert len(var.dependencies) == 1
    dep = var.dependencies[0]
    assert dep.depends_on_type == "tag"
    assert dep.depends_on_tag_id == 5


@pytest.mark.asyncio
async def test_create_rejects_invalid_expression(db_session):
    with pytest.raises(VariableError):
        await _make(db_session, "bad", {"op": "div", "args": [_scalar_const(), _scalar_const()]})


@pytest.mark.asyncio
async def test_update_bumps_version_on_expression_change(db_session):
    var = await _make(db_session, "v2", _scalar_const(1.0))
    updated = await update_variable(
        db_session, var.id, name="v2", description="", unit="",
        expression=_scalar_const(2.0), null_policy="skip", quality_policy="good_only",
        default_time_grain="day", updated_by=1,
    )
    assert updated.version == 2
    assert json.loads(updated.expression_json)["value"] == 2.0


@pytest.mark.asyncio
async def test_update_no_bump_on_cosmetic_change(db_session):
    var = await _make(db_session, "v3", _scalar_const(1.0))
    updated = await update_variable(
        db_session, var.id, name="renamed", description="desc", unit="",
        expression=_scalar_const(1.0), null_policy="skip", quality_policy="good_only",
        default_time_grain="day", updated_by=1,
    )
    assert updated.version == 1
    assert updated.name == "renamed"


@pytest.mark.asyncio
async def test_create_rejects_direct_cycle(db_session):
    a = await _make(db_session, "a", _scalar_const(1.0))
    b = await _make(db_session, "b", {"op": "ref", "variable_id": a.id})
    # now make a reference b → cycle a→b→a
    with pytest.raises(VariableError, match="döngü|cycle"):
        await update_variable(
            db_session, a.id, name="a", description="", unit="",
            expression={"op": "ref", "variable_id": b.id},
            null_policy="skip", quality_policy="good_only",
            default_time_grain="day", updated_by=1,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_service.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.service'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/facility_variables/service.py`:

```python
"""Tesis değişkeni servis katmanı: CRUD, bağımlılık saklama, döngü reddi."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable, FacilityVariableDependency
from app.services.facility_variables.expression import (
    ExpressionError,
    extract_dependencies,
    validate_expression,
)

# version'ı artıran alanlar (kozmetik olmayanlar).
_VERSION_FIELDS = ("expression_json", "null_policy", "quality_policy", "default_time_grain")


class VariableError(ValueError):
    """Doğrulama veya döngü hatası."""


async def would_create_cycle(
    db: AsyncSession, var_id: int | None, dep_var_ids: list[int]
) -> bool:
    """dep_var_ids'den var_id'ye ulaşan bir yol varsa True (döngü)."""
    if var_id is None:
        return False
    # Bağımlılık grafiğini variable→variable kenarları üzerinden gez.
    rows = await db.execute(
        select(
            FacilityVariableDependency.variable_id,
            FacilityVariableDependency.depends_on_variable_id,
        ).where(FacilityVariableDependency.depends_on_type == "variable")
    )
    edges: dict[int, list[int]] = {}
    for src, dst in rows.all():
        if dst is not None:
            edges.setdefault(src, []).append(dst)

    stack = list(dep_var_ids)
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur == var_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(edges.get(cur, []))
    return False


async def _store_dependencies(db: AsyncSession, var: FacilityVariable, expression: dict) -> None:
    deps = extract_dependencies(expression)
    dep_var_ids = [vid for (t, _tid, vid) in deps if t == "variable" and vid is not None]
    if await would_create_cycle(db, var.id, dep_var_ids):
        raise VariableError("Bağımlılık döngüsü (cycle) reddedildi")
    # Mevcut bağımlılıkları temizle, yenilerini yaz.
    var.dependencies.clear()
    for dtype, tag_id, variable_id in deps:
        var.dependencies.append(
            FacilityVariableDependency(
                depends_on_type=dtype,
                depends_on_tag_id=tag_id,
                depends_on_variable_id=variable_id,
            )
        )


async def create_variable(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    description: str,
    kind: str,
    unit: str,
    expression: dict,
    null_policy: str,
    quality_policy: str,
    default_time_grain: str | None,
    value_type: str,
    created_by: int | None,
) -> FacilityVariable:
    try:
        validate_expression(expression, kind)
    except ExpressionError as e:
        raise VariableError(str(e)) from e

    var = FacilityVariable(
        code=code,
        name=name,
        description=description,
        kind=kind,
        value_type=value_type,
        unit=unit,
        expression_json=json.dumps(expression),
        null_policy=null_policy,
        quality_policy=quality_policy,
        default_time_grain=default_time_grain,
        version=1,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(var)
    await db.flush()  # var.id gerekli (bağımlılıklar için)
    await _store_dependencies(db, var, expression)
    await db.commit()
    await db.refresh(var)
    return var


async def update_variable(
    db: AsyncSession,
    var_id: int,
    *,
    name: str,
    description: str,
    unit: str,
    expression: dict,
    null_policy: str,
    quality_policy: str,
    default_time_grain: str | None,
    updated_by: int | None,
) -> FacilityVariable:
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise VariableError("Değişken bulunamadı")
    try:
        validate_expression(expression, var.kind)
    except ExpressionError as e:
        raise VariableError(str(e)) from e

    new_expr = json.dumps(expression)
    bump = (
        new_expr != var.expression_json
        or null_policy != var.null_policy
        or quality_policy != var.quality_policy
        or default_time_grain != var.default_time_grain
    )
    var.name = name
    var.description = description
    var.unit = unit
    var.expression_json = new_expr
    var.null_policy = null_policy
    var.quality_policy = quality_policy
    var.default_time_grain = default_time_grain
    var.updated_by = updated_by
    if bump:
        var.version += 1
    await _store_dependencies(db, var, expression)
    await db.commit()
    await db.refresh(var)
    return var


async def deactivate_variable(db: AsyncSession, var_id: int) -> FacilityVariable:
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise VariableError("Değişken bulunamadı")
    var.is_active = False
    await db.commit()
    await db.refresh(var)
    return var
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_service.py -n0`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/service.py \
        scada-reporter/backend/tests/test_facility_variable_service.py
git commit -m "feat(facility-vars): service layer with dependency storage + cycle rejection"
```

---

### Task 7: Preview layer with hard bounds

**Files:**
- Create: `scada-reporter/backend/app/services/facility_variables/preview.py`
- Test: `scada-reporter/backend/tests/test_facility_variable_preview.py`

**Interfaces:**
- Consumes: `engine.evaluate`, models.
- Produces:
  - `class PreviewBoundsError(ValueError)` (maps to HTTP 422 at the API layer)
  - `MAX_PREVIEW_POINTS = 5000`
  - `estimate_points(start, end, grain) -> int`
  - `check_preview_bounds(start, end, grain) -> None` — raises `PreviewBoundsError` if the window would exceed `MAX_PREVIEW_POINTS`
  - `async preview_variable(db, var, *, start, end, grain, tz_offset_hours) -> dict` — returns `{"kind": "scalar", "value": ..., "unit": ...}` or `{"kind": "series", "points": [{"ts": iso_with_offset, "value": ...}], "unit": ...}`. Resolves `ref` recursively against active variables.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_preview.py`:

```python
from datetime import datetime

import pytest

from app.services.facility_variables.preview import (
    PreviewBoundsError,
    check_preview_bounds,
    estimate_points,
    preview_variable,
)
from app.services.facility_variables.service import create_variable


def test_estimate_points_minute_year_is_huge():
    n = estimate_points(datetime(2026, 1, 1), datetime(2027, 1, 1), "hour")
    assert n >= 8000


def test_check_bounds_rejects_oversized():
    with pytest.raises(PreviewBoundsError):
        check_preview_bounds(datetime(2026, 1, 1), datetime(2027, 1, 1), "hour")


def test_check_bounds_allows_month_daily():
    check_preview_bounds(datetime(2026, 6, 1), datetime(2026, 7, 1), "day")  # no raise


@pytest.mark.asyncio
async def test_preview_scalar(db_session):
    var = await create_variable(
        db_session, code="p1", name="p1", description="", kind="scalar", unit="m3/gun",
        expression={"op": "const", "value": 42.0}, null_policy="skip",
        quality_policy="good_only", default_time_grain="day", value_type="number", created_by=1,
    )
    out = await preview_variable(
        db_session, var, start=datetime(2026, 6, 1), end=datetime(2026, 7, 1),
        grain="day", tz_offset_hours=3,
    )
    assert out["kind"] == "scalar"
    assert out["value"] == 42.0
    assert out["unit"] == "m3/gun"


@pytest.mark.asyncio
async def test_preview_series_emits_offset_ts(db_session):
    from app.models.tag import Tag, TagReading

    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 0), value=0.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 23), value=40.0))
    await db_session.commit()

    var = await create_variable(
        db_session, code="p2", name="p2", description="", kind="series", unit="m3/gun",
        expression={"op": "series", "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta", "grain": "day", "window": "2d"},
        null_policy="skip", quality_policy="good_only", default_time_grain="day",
        value_type="number", created_by=1,
    )
    out = await preview_variable(
        db_session, var, start=datetime(2026, 6, 1), end=datetime(2026, 6, 3),
        grain="day", tz_offset_hours=3,
    )
    assert out["kind"] == "series"
    assert out["points"][0]["ts"].endswith("+03:00")
    assert out["points"][0]["value"] == 40.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variable_preview.py -n0`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facility_variables.preview'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/facility_variables/preview.py`:

```python
"""Önizleme katmanı: sınırlı pencere değerlendirmesi + ref özyineleme + tz'li ts.

Cache yok (v1) → pencere sert sınırlanır, aksi halde UI tetikli DB DoS.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.engine import EvalResult, evaluate

MAX_PREVIEW_POINTS = 5000

_GRAIN_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,  # ~30 gün yaklaşık
}


class PreviewBoundsError(ValueError):
    """Önizleme penceresi izinli sınırı aşıyor."""


def estimate_points(start: datetime, end: datetime, grain: str) -> int:
    seconds = max(0.0, (end - start).total_seconds())
    step = _GRAIN_SECONDS.get(grain, 86400)
    return int(seconds // step) + 1


def check_preview_bounds(start: datetime, end: datetime, grain: str) -> None:
    if end <= start:
        raise PreviewBoundsError("end, start'tan sonra olmalı")
    if estimate_points(start, end, grain) > MAX_PREVIEW_POINTS:
        raise PreviewBoundsError(
            f"Önizleme çok geniş: > {MAX_PREVIEW_POINTS} nokta. Pencereyi daralt veya grain'i büyüt."
        )


def _iso_offset(dt: datetime, tz_offset_hours: int) -> str:
    tz = timezone(timedelta(hours=tz_offset_hours))
    return dt.replace(tzinfo=tz).isoformat()


async def preview_variable(
    db: AsyncSession,
    var: FacilityVariable,
    *,
    start: datetime,
    end: datetime,
    grain: str,
    tz_offset_hours: int,
) -> dict:
    check_preview_bounds(start, end, grain)
    expression = json.loads(var.expression_json)

    async def resolve_ref(variable_id: int) -> EvalResult:
        ref_var = await db.get(FacilityVariable, variable_id)
        if ref_var is None or not ref_var.is_active:
            return EvalResult(kind="scalar", scalar=None)
        ref_expr = json.loads(ref_var.expression_json)
        return await evaluate(
            db, ref_expr, start=start, end=end, grain=grain,
            tz_offset_hours=tz_offset_hours, resolve_ref=resolve_ref,
        )

    result = await evaluate(
        db, expression, start=start, end=end, grain=grain,
        tz_offset_hours=tz_offset_hours, resolve_ref=resolve_ref,
    )

    if result.kind == "scalar":
        return {"kind": "scalar", "value": result.scalar, "unit": var.unit}
    points = [
        {"ts": _iso_offset(k, tz_offset_hours), "value": v}
        for k, v in sorted((result.series or {}).items())
    ]
    return {"kind": "series", "points": points, "unit": var.unit}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variable_preview.py -n0`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/services/facility_variables/preview.py \
        scada-reporter/backend/tests/test_facility_variable_preview.py
git commit -m "feat(facility-vars): preview layer with hard bounds + ref recursion"
```

---

### Task 8: API router — CRUD, validate, preview, dependencies

**Files:**
- Create: `scada-reporter/backend/app/api/facility_variables.py`
- Modify: `scada-reporter/backend/app/main.py` (register router)
- Test: `scada-reporter/backend/tests/test_facility_variables_api.py`

**Interfaces:**
- Consumes: `service.*`, `preview.*`, `expression.validate_expression`, `require_perm`, `require_writable`, `get_current_user`, `get_db`, `settings.REPORT_TZ_OFFSET_HOURS`.
- Produces the routes (prefix `/facility-variables`):
  - `GET ""` → list (any user)
  - `POST ""` → create (perm `facility_variable:create` + `require_writable`), 201
  - `GET "/{id}"` → detail
  - `PUT "/{id}"` → update (perm `facility_variable:edit` + `require_writable`)
  - `DELETE "/{id}"` → soft delete via deactivate (perm `facility_variable:delete` + `require_writable`), 204
  - `POST "/validate"` → validate a candidate expression body (any user)
  - `POST "/{id}/preview"` → preview with window body (any user)
  - `GET "/{id}/dependencies"` → flat dependency list (any user)

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variables_api.py`:

```python
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.api.license_guard import require_writable
from app.main import app


@pytest_asyncio.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="admin", role="admin", permission_overrides={}, is_active=True
    )
    app.dependency_overrides[require_writable] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_writable, None)


def _const_payload(code, value=1.0):
    return {
        "code": code, "name": code, "description": "", "kind": "scalar",
        "unit": "m3/gun", "expression": {"op": "const", "value": value},
        "null_policy": "skip", "quality_policy": "good_only",
        "default_time_grain": "day", "value_type": "number",
    }


@pytest.mark.asyncio
async def test_create_and_get(client):
    resp = await client.post("/api/facility-variables", json=_const_payload("v1"))
    assert resp.status_code == 201
    vid = resp.json()["id"]

    got = await client.get(f"/api/facility-variables/{vid}")
    assert got.status_code == 200
    assert got.json()["code"] == "v1"
    assert got.json()["version"] == 1


@pytest.mark.asyncio
async def test_create_invalid_expression_422(client):
    bad = _const_payload("bad")
    bad["expression"] = {"op": "div", "args": [{"op": "const", "value": 1}, {"op": "const", "value": 2}]}
    resp = await client.post("/api/facility-variables", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_endpoint(client):
    resp = await client.post(
        "/api/facility-variables/validate",
        json={"expression": {"op": "const", "value": 1}, "kind": "scalar"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_preview_scalar(client):
    await client.post("/api/facility-variables", json=_const_payload("p1", 42.0))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.post(
        f"/api/facility-variables/{vid}/preview",
        json={"window": {"type": "month", "year": 2026, "month": 6}, "grain": "day"},
    )
    assert resp.status_code == 200
    assert resp.json()["kind"] == "scalar"
    assert resp.json()["value"] == 42.0


@pytest.mark.asyncio
async def test_preview_bounds_422(client):
    await client.post("/api/facility-variables", json=_const_payload("p2"))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.post(
        f"/api/facility-variables/{vid}/preview",
        json={"window": {"type": "custom", "start": "2026-01-01T00:00:00", "end": "2027-01-01T00:00:00"}, "grain": "hour"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_soft_delete(client):
    await client.post("/api/facility-variables", json=_const_payload("d1"))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.delete(f"/api/facility-variables/{vid}")
    assert resp.status_code == 204
    got = await client.get(f"/api/facility-variables/{vid}")
    assert got.json()["is_active"] is False


@pytest.mark.asyncio
async def test_dependencies_endpoint(client):
    payload = _const_payload("dep1")
    payload["kind"] = "scalar"
    payload["expression"] = {"op": "agg", "source": {"type": "tag", "tag_id": 5}, "agg": "delta", "window": "day"}
    await client.post("/api/facility-variables", json=payload)
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.get(f"/api/facility-variables/{vid}/dependencies")
    assert resp.status_code == 200
    deps = resp.json()
    assert any(d["depends_on_type"] == "tag" and d["depends_on_tag_id"] == 5 for d in deps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_facility_variables_api.py -n0`
Expected: FAIL with `404` (router not registered) / import error.

- [ ] **Step 3: Write minimal implementation**

Create `app/api/facility_variables.py`:

```python
"""Tesis değişkenleri REST API: CRUD + validate + preview + dependencies."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_perm
from app.api.license_guard import require_writable
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import (
    PERM_FACILITY_VARIABLE_CREATE,
    PERM_FACILITY_VARIABLE_DELETE,
    PERM_FACILITY_VARIABLE_EDIT,
)
from app.models.facility_variable import FacilityVariable
from app.models.user import User
from app.services.facility_variables.expression import ExpressionError, validate_expression
from app.services.facility_variables.preview import PreviewBoundsError, preview_variable
from app.services.facility_variables.service import (
    VariableError,
    create_variable,
    deactivate_variable,
    update_variable,
)

router = APIRouter(prefix="/facility-variables", tags=["facility-variables"])


# --------------------------------------------------------------------------- schemas
class VariableCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    kind: str
    unit: str = ""
    value_type: str = "number"
    expression: dict
    null_policy: str = "skip"
    quality_policy: str = "good_only"
    default_time_grain: str | None = "day"


class VariableUpdate(BaseModel):
    name: str
    description: str = ""
    unit: str = ""
    expression: dict
    null_policy: str = "skip"
    quality_policy: str = "good_only"
    default_time_grain: str | None = "day"


class VariableResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    kind: str
    value_type: str
    unit: str
    expression: dict
    null_policy: str
    quality_policy: str
    default_time_grain: str | None
    is_active: bool
    version: int
    dependency_count: int

    @classmethod
    def of(cls, v: FacilityVariable) -> "VariableResponse":
        return cls(
            id=v.id, code=v.code, name=v.name, description=v.description, kind=v.kind,
            value_type=v.value_type, unit=v.unit, expression=json.loads(v.expression_json),
            null_policy=v.null_policy, quality_policy=v.quality_policy,
            default_time_grain=v.default_time_grain, is_active=v.is_active,
            version=v.version, dependency_count=len(v.dependencies),
        )


class ValidateRequest(BaseModel):
    expression: dict
    kind: str


class WindowSpec(BaseModel):
    type: str  # month|last_24h|last_7d|last_30d|custom
    year: int | None = None
    month: int | None = None
    start: datetime | None = None
    end: datetime | None = None


class PreviewRequest(BaseModel):
    window: WindowSpec
    grain: str | None = None
    tz_offset_hours: int | None = None


# --------------------------------------------------------------------------- helpers
def _resolve_window(w: WindowSpec) -> tuple[datetime, datetime]:
    if w.type == "month":
        if w.year is None or w.month is None:
            raise HTTPException(422, "month penceresi year+month ister")
        start = datetime(w.year, w.month, 1)
        end = datetime(w.year + 1, 1, 1) if w.month == 12 else datetime(w.year, w.month + 1, 1)
        return start, end
    if w.type == "custom":
        if w.start is None or w.end is None:
            raise HTTPException(422, "custom penceresi start+end ister")
        return w.start.replace(tzinfo=None), w.end.replace(tzinfo=None)
    raise HTTPException(422, f"Desteklenmeyen window tipi: {w.type}")


# --------------------------------------------------------------------------- routes
@router.get("", response_model=list[VariableResponse])
async def list_variables(
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    rows = await db.execute(select(FacilityVariable).order_by(FacilityVariable.code))
    return [VariableResponse.of(v) for v in rows.scalars().all()]


@router.post("", response_model=VariableResponse, status_code=201)
async def create(
    body: VariableCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm(PERM_FACILITY_VARIABLE_CREATE)),
    _w: None = Depends(require_writable),
):
    try:
        var = await create_variable(
            db, code=body.code, name=body.name, description=body.description, kind=body.kind,
            unit=body.unit, expression=body.expression, null_policy=body.null_policy,
            quality_policy=body.quality_policy, default_time_grain=body.default_time_grain,
            value_type=body.value_type, created_by=user.id,
        )
    except VariableError as e:
        raise HTTPException(422, str(e)) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(409, "Bu code zaten var") from e
    return VariableResponse.of(var)


@router.get("/{var_id}", response_model=VariableResponse)
async def detail(var_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    return VariableResponse.of(var)


@router.put("/{var_id}", response_model=VariableResponse)
async def update(
    var_id: int,
    body: VariableUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm(PERM_FACILITY_VARIABLE_EDIT)),
    _w: None = Depends(require_writable),
):
    try:
        var = await update_variable(
            db, var_id, name=body.name, description=body.description, unit=body.unit,
            expression=body.expression, null_policy=body.null_policy,
            quality_policy=body.quality_policy, default_time_grain=body.default_time_grain,
            updated_by=user.id,
        )
    except VariableError as e:
        raise HTTPException(422, str(e)) from e
    return VariableResponse.of(var)


@router.delete("/{var_id}", status_code=204)
async def soft_delete(
    var_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm(PERM_FACILITY_VARIABLE_DELETE)),
    _w: None = Depends(require_writable),
):
    try:
        await deactivate_variable(db, var_id)
    except VariableError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/validate")
async def validate(body: ValidateRequest, _: User = Depends(get_current_user)):
    try:
        validate_expression(body.expression, body.kind)
    except ExpressionError as e:
        raise HTTPException(422, str(e)) from e
    return {"valid": True}


@router.post("/{var_id}/preview")
async def preview(
    var_id: int,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    start, end = _resolve_window(body.window)
    grain = body.grain or var.default_time_grain or "day"
    tz = body.tz_offset_hours if body.tz_offset_hours is not None else settings.REPORT_TZ_OFFSET_HOURS
    try:
        return await preview_variable(db, var, start=start, end=end, grain=grain, tz_offset_hours=tz)
    except PreviewBoundsError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{var_id}/dependencies")
async def dependencies(
    var_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise HTTPException(404, "Değişken bulunamadı")
    return [
        {
            "depends_on_type": d.depends_on_type,
            "depends_on_tag_id": d.depends_on_tag_id,
            "depends_on_variable_id": d.depends_on_variable_id,
        }
        for d in var.dependencies
    ]
```

In `app/main.py`, add `facility_variables` to the `from app.api import (...)` block and register the router after `excel_templates`:

```python
app.include_router(facility_variables.router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_facility_variables_api.py -n0`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full backend suite + checks**

Run: `cd scada-reporter/backend && just check && python -m pytest -n0 -q`
Expected: ruff/mypy/format clean; all tests pass (existing + new).

- [ ] **Step 6: Commit**

```bash
git add scada-reporter/backend/app/api/facility_variables.py \
        scada-reporter/backend/app/main.py \
        scada-reporter/backend/tests/test_facility_variables_api.py
git commit -m "feat(facility-vars): CRUD + validate + preview + dependencies API"
```

---

### Task 9: Parity test — engine ≡ daily_rollup

**Files:**
- Test: `scada-reporter/backend/tests/test_facility_variable_parity.py`

**Interfaces:**
- Consumes: `daily_rollup.daily_values`, `engine.evaluate` / `buckets.bucket_series`. No new production code — this task locks in the spec's core invariant ("engine and `daily_rollup` must not diverge on the same `(tag, agg, window)`").

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_facility_variable_parity.py`:

```python
from datetime import datetime

import pytest

from app.models.tag import Tag, TagReading
from app.services.facility_variables.buckets import bucket_series
from app.services.template_fill.daily_rollup import daily_values


@pytest.mark.asyncio
@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max", "last", "delta"])
async def test_bucket_series_matches_daily_values(db_session, agg):
    tag = Tag(node_id="n", name="T", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    # spread readings across June 1-3 with multiple per day
    rows = [
        (datetime(2026, 6, 1, 1), 10.0), (datetime(2026, 6, 1, 13), 30.0), (datetime(2026, 6, 1, 22), 55.0),
        (datetime(2026, 6, 2, 2), 60.0), (datetime(2026, 6, 2, 20), 90.0),
        (datetime(2026, 6, 3, 5), 95.0), (datetime(2026, 6, 3, 18), 120.0),
    ]
    for ts, val in rows:
        db_session.add(TagReading(tag_id=tag.id, timestamp=ts, value=val))
    await db_session.commit()

    offset = 3
    legacy = await daily_values(db_session, tag.id, 2026, 6, agg, tz_offset_hours=offset)
    engine_out = await bucket_series(
        db_session, tag.id, datetime(2026, 6, 1), datetime(2026, 7, 1), "day", agg, offset
    )
    # re-key engine output {date -> v} to {day_no -> v} for comparison
    engine_by_day = {k.day: v for k, v in engine_out.items()}
    assert engine_by_day == legacy
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_facility_variable_parity.py -n0`
Expected: PASS. (If it FAILS, the bucketing diverges from `daily_rollup` — fix `buckets.py` before continuing; do not weaken the test.)

- [ ] **Step 3: Commit**

```bash
git add scada-reporter/backend/tests/test_facility_variable_parity.py
git commit -m "test(facility-vars): lock engine≡daily_rollup parity across all aggs"
```

---

## Self-Review

**1. Spec coverage (Plan 1 scope = backend foundation):**
- Variable model + dependencies table → Task 2 ✓
- `version` bump contract → Task 6 (`update_variable` bump logic) ✓
- Expression ops `agg/add/sub/mul/div/const/round/abs/coalesce/series/moving_avg/reduce/ref` → Tasks 3 (validate) + 5 (evaluate) ✓
- `delta` mandatory + totalizer → Tasks 4/5/9 ✓
- `div on_zero` → Tasks 3 (validate) + 5 (evaluate) ✓
- Operand-null SQL-like propagation + `coalesce` → Task 5 ✓
- Shape algebra (scalar/series/broadcast/align) → Tasks 3 (infer) + 5 (evaluate) ✓
- tz offset on every bucket → Tasks 4/5/9 ✓
- Output shape contract `{day_no/bucket: value}` → Task 4 (`bucket_series`) + Task 9 parity ✓
- Quality policy propagation (`ref` = leaf-level) → Task 7 `resolve_ref` consumes computed result, no re-filter ✓ (full quality filtering of leaf reads is deferred — see gap below)
- Roll-up sources per grain → Task 4 (Python bucketing; PG cagg routing deferred to Plan 2, noted) ✓
- Permissions registration (3 places) → Task 1 (catalog) + Task 8 (endpoints); frontend = Plan 4 ✓
- CRUD + validate + preview + dependencies API → Task 8 ✓
- Preview hard bounds (422) → Task 7 + Task 8 ✓
- Soft delete via `is_active` → Tasks 6/8 ✓
- Cycle rejection → Task 6 ✓
- Parity invariant → Task 9 ✓

**Known deferrals (carried to later plans, not gaps in Plan 1):**
- `quality_policy` actual reading filter: `daily_rollup`/`buckets` don't filter by quality yet (spec acknowledges this). Plan 1 stores the policy and propagates it structurally; wiring the leaf read filter is folded into Plan 2 alongside the PG cagg path so both dialects change together. Engine `evaluate` already receives the variable's policy via the variable record — add the `quality_policy` parameter to `bucket_series`/`agg_window` there.
- Excel binding fields (`source_type`, `variable_id`, `write_mode`, `reduce_op`, `target_mode`, `target_cell`, `variable_code_snapshot`), dangling-binding guard, kind-lock-while-bound → **Plan 2**.
- Archive `variable_refs_json` / version stamping → **Plan 3**.
- Unit compatibility (`facility_variable_units.py`, warn on incompatible) → **Plan 2** (cheap, additive at create/update validation).
- Advanced-reports variable selection → **Plan 3**.
- All UI (list/wizard/expression-builder/preview/Excel-mapping/i18n) → **Plan 4**.

**2. Placeholder scan:** No TBD/TODO; every code step has full code; every test step has full assertions. ✓

**3. Type consistency:** `EvalResult(kind, scalar, series)` defined in Task 5, consumed identically in Task 7. `evaluate(...)` keyword signature identical across Tasks 5/7. `reduce_values` promoted in Task 4, imported in Task 5. `create_variable(...)` signature defined in Task 6, called identically in Tasks 7/8. Permission constants from Task 1 imported in Task 8. ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-29-facility-variables-backend.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
