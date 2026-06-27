# Lab Data Entry & Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual data-entry feature so lab analysis/measurement results can be entered through a UI, tracked on Grafana, and reported via the existing engine.

**Architecture:** Four new SQLAlchemy tables (`lab_parameter`, `lab_sample_point`, `lab_sample`, `lab_measurement`) model a unified "sample → N measurements" shape. A new `app/api/lab.py` router exposes catalog CRUD, sample entry (single/batch/import), and audited edit/delete. A portable SQL view `v_lab_timeseries` feeds Grafana; parameters with `mirror_to_tag_id` set also write into `tag_readings` so existing SCADA dashboards and `advanced_reports` consume them unchanged. A React `LabEntry` page provides four tabs.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy async / Alembic / pytest-asyncio + xdist; React 19 / Vite / TypeScript / TanStack Query / Tailwind v4 / i18next; OpenAPI-generated TS client.

## Global Constraints

- Python baseline is **3.14** (never lower). Backend only imports cleanly on 3.14.
- Backend tests: `just test` (pytest async, parallel `-n auto`, randomized). Per-file run during TDD: `.venv/Scripts/python -m pytest tests/<file> -p no:randomly -n0 -v`.
- Lint/type gate: `just check` (ruff + mypy + frontend). Run before each commit's final step.
- Single Alembic head must be preserved. Current head: **`46644a7e7f25`**. The new migration's `down_revision = "46644a7e7f25"`.
- New models MUST be imported in `app/main.py` (the `# noqa: F401` block at lines 51-59) so `Base.metadata` registers them for `create_all` (tests) and Alembic autogenerate.
- Router prefix is `/api`; `app.include_router(lab.router, prefix="/api")` in `app/main.py` near line 220.
- RBAC helpers from `app.api.auth`: `get_current_user`, `require_role("admin", "operator")`, `require_perm(...)`. Write-gating from `app.api.license_guard`: `require_writable` (blocks demo read-only).
- Audit via `app.core.audit.record_audit(db, actor=..., action=..., target_type=..., target_id=..., detail=..., ip=...)` — adds row to session, caller commits.
- Timestamps stored naive-UTC to match `tag_readings.timestamp` (the mirror target).
- Frontend: do NOT run `prettier --write` (project uses compact style). Regenerate the TS client with `just gen-client` while the backend runs. New i18n namespace must be registered in 3 places in `src/i18n/index.ts` (import + each language's resources object + ns array) for all 5 languages (en/tr/ru/de/ar).

---

## File Structure

**Backend (create):**
- `app/models/lab.py` — the 4 ORM models.
- `app/api/lab.py` — the `/api/lab` router (catalog + samples + import).
- `app/services/lab_import.py` — Excel/CSV parsing + column mapping (keeps the router thin).
- `alembic/versions/<rev>_lab_data_entry.py` — tables + indexes + `v_lab_timeseries` view.
- `tests/test_lab_models.py`, `tests/test_lab_catalog.py`, `tests/test_lab_samples.py`, `tests/test_lab_edit_delete.py`, `tests/test_lab_import.py`, `tests/test_lab_view.py`.

**Backend (modify):**
- `app/main.py` — import lab model + include lab router.

**Grafana (create):**
- `scada-reporter/docker/grafana/dashboards/lab-quality.json`.

**Frontend (create):**
- `src/pages/LabEntry.tsx` + tab components under `src/pages/lab/`.
- `src/i18n/locales/{en,tr,ru,de,ar}/lab.json`.
- `src/pages/lab/LabEntry.test.tsx` (vitest).

**Frontend (modify):**
- `src/i18n/index.ts`, `src/components/Layout.tsx` (sidebar + route), `src/App.tsx` (route), `src/pages/Settings.tsx` (catalog card), `src/api/client.ts` (regenerated).

---

## Task 1: Lab data model + migration

**Files:**
- Create: `scada-reporter/backend/app/models/lab.py`
- Create: `scada-reporter/backend/alembic/versions/a1b2c3d4e5f7_lab_data_entry.py`
- Modify: `scada-reporter/backend/app/main.py` (model import in the noqa block)
- Test: `scada-reporter/backend/tests/test_lab_models.py`

**Interfaces:**
- Produces: ORM classes `LabParameter`, `LabSamplePoint`, `LabSample`, `LabMeasurement` (module `app.models.lab`). Key fields used by later tasks:
  - `LabParameter(id, code, name, unit, category, min_limit: float|None, max_limit: float|None, is_active: bool, approved: bool, mirror_to_tag_id: int|None)`
  - `LabSamplePoint(id, code, name, description, is_active, approved)`
  - `LabSample(id, sample_point_id, sampled_at: datetime, entered_by: int, method, batch_no, note, created_at)`
  - `LabMeasurement(id, sample_id, parameter_id, value: float|None, text_value: str|None, flag: str|None)`

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_models.py`:

```python
import pytest
from sqlalchemy import select

from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint
from datetime import datetime


@pytest.mark.asyncio
async def test_sample_with_measurements_roundtrip(db_session):
    param = LabParameter(code="PH", name="pH", unit="", min_limit=6.5, max_limit=9.0)
    point = LabSamplePoint(code="INLET", name="Inlet")
    db_session.add_all([param, point])
    await db_session.flush()

    sample = LabSample(
        sample_point_id=point.id,
        sampled_at=datetime(2026, 6, 27, 9, 0, 0),
        entered_by=1,
        method="titration",
        batch_no="B1",
        note="",
    )
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=7.2))
    await db_session.commit()

    rows = (await db_session.execute(select(LabMeasurement))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == 7.2
    # defaults
    assert param.is_active is True
    assert param.approved is True
    assert param.mirror_to_tag_id is None


@pytest.mark.asyncio
async def test_deleting_sample_cascades_measurements(db_session):
    point = LabSamplePoint(code="OUT", name="Outlet")
    param = LabParameter(code="COD", name="COD", unit="mg/L")
    db_session.add_all([point, param])
    await db_session.flush()
    sample = LabSample(sample_point_id=point.id, sampled_at=datetime(2026, 6, 27, 9, 0), entered_by=1)
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=320.0))
    await db_session.commit()

    await db_session.delete(sample)
    await db_session.commit()
    rows = (await db_session.execute(select(LabMeasurement))).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_models.py -p no:randomly -n0 -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.lab'`.

- [ ] **Step 3: Write the model module**

Create `scada-reporter/backend/app/models/lab.py`:

```python
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LabParameter(Base):
    __tablename__ = "lab_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    min_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    # Hybrid catalog: operator-added entries land approved=False, awaiting admin.
    approved: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    # Optional mirror into tag_readings for same-panel SCADA comparison + reports.
    mirror_to_tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )


class LabSamplePoint(Base):
    __tablename__ = "lab_sample_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    approved: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)


class LabSample(Base):
    __tablename__ = "lab_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_sample_points.id"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    entered_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(255), default="")
    batch_no: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    measurements: Mapped[list["LabMeasurement"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class LabMeasurement(Base):
    __tablename__ = "lab_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_samples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_parameters.id"), nullable=False, index=True
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    sample: Mapped[LabSample] = relationship(back_populates="measurements")
```

Then register the model for metadata. In `scada-reporter/backend/app/main.py`, add to the `# noqa: F401` import block (after line 53, alphabetical-ish is fine):

```python
from app.models import lab as _lab  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_models.py -p no:randomly -n0 -v`
Expected: PASS (2 passed). Tables are auto-created from `Base.metadata` by the conftest `db_engine` fixture.

- [ ] **Step 5: Generate the Alembic migration**

Create `scada-reporter/backend/alembic/versions/a1b2c3d4e5f7_lab_data_entry.py` (hand-written for determinism — the view is not autogenerated):

```python
"""lab data entry tables + v_lab_timeseries view

Revision ID: a1b2c3d4e5f7
Revises: 46644a7e7f25
Create Date: 2026-06-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "46644a7e7f25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEW_SQL = """
CREATE VIEW v_lab_timeseries AS
SELECT
    ls.sampled_at      AS time,
    sp.code            AS point_code,
    lp.code            AS param_code,
    lp.name            AS param_name,
    lp.unit            AS unit,
    lm.value           AS value,
    lp.min_limit       AS min_limit,
    lp.max_limit       AS max_limit
FROM lab_measurements lm
JOIN lab_samples ls       ON ls.id = lm.sample_id
JOIN lab_parameters lp    ON lp.id = lm.parameter_id
JOIN lab_sample_points sp ON sp.id = ls.sample_point_id
WHERE lm.value IS NOT NULL
"""


def upgrade() -> None:
    op.create_table(
        "lab_parameters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("min_limit", sa.Float(), nullable=True),
        sa.Column("max_limit", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("mirror_to_tag_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["mirror_to_tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "lab_sample_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "lab_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample_point_id", sa.Integer(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(), nullable=False),
        sa.Column("entered_by", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("batch_no", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["sample_point_id"], ["lab_sample_points.id"]),
        sa.ForeignKeyConstraint(["entered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_samples_sampled_at", "lab_samples", ["sampled_at"])
    op.create_index("ix_lab_samples_sample_point_id", "lab_samples", ["sample_point_id"])
    op.create_table(
        "lab_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.String(length=255), nullable=True),
        sa.Column("flag", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["sample_id"], ["lab_samples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parameter_id"], ["lab_parameters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_measurements_sample_id", "lab_measurements", ["sample_id"])
    op.create_index("ix_lab_measurements_parameter_id", "lab_measurements", ["parameter_id"])
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_lab_timeseries")
    op.drop_index("ix_lab_measurements_parameter_id", table_name="lab_measurements")
    op.drop_index("ix_lab_measurements_sample_id", table_name="lab_measurements")
    op.drop_table("lab_measurements")
    op.drop_index("ix_lab_samples_sample_point_id", table_name="lab_samples")
    op.drop_index("ix_lab_samples_sampled_at", table_name="lab_samples")
    op.drop_table("lab_samples")
    op.drop_table("lab_sample_points")
    op.drop_table("lab_parameters")
```

- [ ] **Step 6: Verify migration applies and head is single**

Run: `just migrate` then `.venv/Scripts/python -m alembic heads`
Expected: upgrade runs clean; `alembic heads` prints exactly one head `a1b2c3d4e5f7 (head)`.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/models/lab.py scada-reporter/backend/app/main.py scada-reporter/backend/alembic/versions/a1b2c3d4e5f7_lab_data_entry.py scada-reporter/backend/tests/test_lab_models.py
git commit -m "feat(lab): data model + migration (tables + v_lab_timeseries view)"
```

---

## Task 2: Catalog endpoints (parameters + sample points, hybrid approval)

**Files:**
- Create: `scada-reporter/backend/app/api/lab.py`
- Modify: `scada-reporter/backend/app/main.py` (include router)
- Test: `scada-reporter/backend/tests/test_lab_catalog.py`

**Interfaces:**
- Consumes: models from Task 1; `require_role`, `get_current_user` (auth), `require_writable` (license_guard), `get_db`.
- Produces: `router` (APIRouter prefix `/lab`). Endpoints:
  - `GET /lab/parameters?approved=&active=` → `list[LabParameterOut]`
  - `POST /lab/parameters` → `LabParameterOut` (operator ⇒ `approved=false`; admin ⇒ `approved=true`)
  - `PATCH /lab/parameters/{id}` (admin) → `LabParameterOut`
  - `DELETE /lab/parameters/{id}` (admin) → 204
  - same four for `/lab/sample-points` with `LabSamplePointOut`
  - Pydantic out-models `LabParameterOut`, `LabSamplePointOut` (consumed by later tasks).

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_catalog.py`:

```python
from types import SimpleNamespace

import pytest
from app.api.auth import get_current_user
from app.main import app


def _user(role: str, uid: int = 1):
    return SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: _user(role, uid)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_creates_approved_parameter(client):
    _as("admin")
    resp = await client.post("/api/lab/parameters", json={"code": "PH", "name": "pH"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["approved"] is True
    assert body["code"] == "PH"


@pytest.mark.asyncio
async def test_operator_created_parameter_is_unapproved(client):
    _as("operator", uid=5)
    resp = await client.post("/api/lab/parameters", json={"code": "COD", "name": "COD", "unit": "mg/L"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["approved"] is False


@pytest.mark.asyncio
async def test_admin_approves_parameter(client):
    _as("operator", uid=5)
    created = (await client.post("/api/lab/parameters", json={"code": "TSS", "name": "TSS"})).json()
    _as("admin")
    resp = await client.patch(f"/api/lab/parameters/{created['id']}", json={"approved": True, "max_limit": 30.0})
    assert resp.status_code == 200
    assert resp.json()["approved"] is True
    assert resp.json()["max_limit"] == 30.0


@pytest.mark.asyncio
async def test_list_filters_approved(client):
    _as("operator", uid=5)
    await client.post("/api/lab/parameters", json={"code": "P1", "name": "P1"})  # unapproved
    _as("admin")
    await client.post("/api/lab/parameters", json={"code": "P2", "name": "P2"})  # approved
    resp = await client.get("/api/lab/parameters?approved=true")
    codes = [p["code"] for p in resp.json()]
    assert "P2" in codes and "P1" not in codes


@pytest.mark.asyncio
async def test_operator_cannot_patch_parameter(client):
    _as("admin")
    created = (await client.post("/api/lab/parameters", json={"code": "X", "name": "X"})).json()
    _as("operator", uid=5)
    resp = await client.patch(f"/api/lab/parameters/{created['id']}", json={"name": "Y"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sample_point_crud(client):
    _as("admin")
    created = (await client.post("/api/lab/sample-points", json={"code": "INLET", "name": "Inlet"})).json()
    assert created["approved"] is True
    resp = await client.delete(f"/api/lab/sample-points/{created['id']}")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_catalog.py -p no:randomly -n0 -v`
Expected: FAIL — 404s (router not mounted) / import error.

- [ ] **Step 3: Write the catalog router**

Create `scada-reporter/backend/app/api/lab.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.api.license_guard import require_writable
from app.core.database import get_db
from app.models.lab import LabParameter, LabSamplePoint
from app.models.user import User

router = APIRouter(prefix="/lab", tags=["lab"])


# ---- Pydantic schemas ----
class LabParameterCreate(BaseModel):
    code: str
    name: str
    unit: str = ""
    category: str = ""
    min_limit: float | None = None
    max_limit: float | None = None
    mirror_to_tag_id: int | None = None


class LabParameterUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    category: str | None = None
    min_limit: float | None = None
    max_limit: float | None = None
    is_active: bool | None = None
    approved: bool | None = None
    mirror_to_tag_id: int | None = None


class LabParameterOut(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    category: str
    min_limit: float | None
    max_limit: float | None
    is_active: bool
    approved: bool
    mirror_to_tag_id: int | None
    model_config = {"from_attributes": True}


class LabSamplePointCreate(BaseModel):
    code: str
    name: str
    description: str = ""


class LabSamplePointUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    approved: bool | None = None


class LabSamplePointOut(BaseModel):
    id: int
    code: str
    name: str
    description: str
    is_active: bool
    approved: bool
    model_config = {"from_attributes": True}


# ---- Parameters ----
@router.get("/parameters", response_model=list[LabParameterOut])
async def list_parameters(
    approved: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(LabParameter).order_by(LabParameter.code)
    if approved is not None:
        query = query.where(LabParameter.approved == approved)
    if active is not None:
        query = query.where(LabParameter.is_active == active)
    return (await db.execute(query)).scalars().all()


@router.post("/parameters", response_model=LabParameterOut, status_code=201)
async def create_parameter(
    data: LabParameterCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    exists = await db.execute(select(LabParameter).where(LabParameter.code == data.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Parametre kodu zaten mevcut")
    param = LabParameter(**data.model_dump(), approved=(user.role == "admin"))
    db.add(param)
    await db.commit()
    await db.refresh(param)
    return param


@router.patch("/parameters/{param_id}", response_model=LabParameterOut)
async def update_parameter(
    param_id: int,
    data: LabParameterUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    param = (
        await db.execute(select(LabParameter).where(LabParameter.id == param_id))
    ).scalar_one_or_none()
    if not param:
        raise HTTPException(status_code=404, detail="Parametre bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(param, field, value)
    await db.commit()
    await db.refresh(param)
    return param


@router.delete("/parameters/{param_id}", status_code=204)
async def delete_parameter(
    param_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await db.execute(sa_delete(LabParameter).where(LabParameter.id == param_id))
    await db.commit()


# ---- Sample points ----
@router.get("/sample-points", response_model=list[LabSamplePointOut])
async def list_sample_points(
    approved: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(LabSamplePoint).order_by(LabSamplePoint.code)
    if approved is not None:
        query = query.where(LabSamplePoint.approved == approved)
    if active is not None:
        query = query.where(LabSamplePoint.is_active == active)
    return (await db.execute(query)).scalars().all()


@router.post("/sample-points", response_model=LabSamplePointOut, status_code=201)
async def create_sample_point(
    data: LabSamplePointCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    exists = await db.execute(select(LabSamplePoint).where(LabSamplePoint.code == data.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Nokta kodu zaten mevcut")
    point = LabSamplePoint(**data.model_dump(), approved=(user.role == "admin"))
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


@router.patch("/sample-points/{point_id}", response_model=LabSamplePointOut)
async def update_sample_point(
    point_id: int,
    data: LabSamplePointUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    point = (
        await db.execute(select(LabSamplePoint).where(LabSamplePoint.id == point_id))
    ).scalar_one_or_none()
    if not point:
        raise HTTPException(status_code=404, detail="Nokta bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(point, field, value)
    await db.commit()
    await db.refresh(point)
    return point


@router.delete("/sample-points/{point_id}", status_code=204)
async def delete_sample_point(
    point_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
    _w=Depends(require_writable),
):
    await db.execute(sa_delete(LabSamplePoint).where(LabSamplePoint.id == point_id))
    await db.commit()
```

In `scada-reporter/backend/app/main.py`, add near the other includes (after line 220 `app.include_router(grafana.router, prefix="/api")`):

```python
from app.api import lab  # noqa: E402  (add to the api import group near the top)
app.include_router(lab.router, prefix="/api")
```

> NOTE: place the `from app.api import lab` import alongside the other `from app.api import ...` lines at the top of `main.py`, and the `include_router` call in the include block. Match the existing style.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_catalog.py -p no:randomly -n0 -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/lab.py scada-reporter/backend/app/main.py scada-reporter/backend/tests/test_lab_catalog.py
git commit -m "feat(lab): catalog endpoints with hybrid approval"
```

---

## Task 3: Sample entry (single + batch) with flag + mirror

**Files:**
- Modify: `scada-reporter/backend/app/api/lab.py`
- Test: `scada-reporter/backend/tests/test_lab_samples.py`

**Interfaces:**
- Consumes: Task 1 models, Task 2 router/auth.
- Produces:
  - helper `compute_flag(value: float | None, min_limit: float | None, max_limit: float | None) -> str | None`
  - `POST /lab/samples` (body `SampleCreate`) → `SampleOut`
  - `POST /lab/samples/batch` (body `{rows: list[SampleCreate]}`) → `{inserted: int, sample_ids: list[int]}`
  - schemas `MeasurementIn(parameter_id:int, value:float|None=None, text_value:str|None=None)`, `SampleCreate(sample_point_id:int, sampled_at:datetime, method:str="", batch_no:str="", note:str="", measurements:list[MeasurementIn])`, `MeasurementOut`, `SampleOut` (used by Task 4).

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_samples.py`:

```python
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.lab import LabParameter, LabSamplePoint
from app.models.tag import Tag, TagReading


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def _seed_point(db_session, code="INLET"):
    p = LabSamplePoint(code=code, name=code)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _seed_param(db_session, code="PH", **kw):
    param = LabParameter(code=code, name=code, **kw)
    db_session.add(param)
    await db_session.commit()
    await db_session.refresh(param)
    return param


@pytest.mark.asyncio
async def test_create_multi_parameter_sample(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH", min_limit=6.5, max_limit=9.0)
    cod = await _seed_param(db_session, code="COD", max_limit=400.0)
    _as("operator", uid=7)
    resp = await client.post("/api/lab/samples", json={
        "sample_point_id": point.id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [
            {"parameter_id": ph.id, "value": 7.2},
            {"parameter_id": cod.id, "value": 320.0},
        ],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entered_by"] == 7
    assert len(body["measurements"]) == 2
    flags = {m["parameter_id"]: m["flag"] for m in body["measurements"]}
    assert flags[ph.id] is None
    assert flags[cod.id] is None


@pytest.mark.asyncio
async def test_over_limit_sets_flag(client, db_session):
    point = await _seed_point(db_session)
    cod = await _seed_param(db_session, code="COD", max_limit=400.0)
    _as("operator", uid=7)
    resp = await client.post("/api/lab/samples", json={
        "sample_point_id": point.id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [{"parameter_id": cod.id, "value": 999.0}],
    })
    assert resp.json()["measurements"][0]["flag"] == "over_limit"


@pytest.mark.asyncio
async def test_mirror_writes_tag_reading(client, db_session):
    tag = Tag(node_id="lab:ph", name="Lab pH")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH", mirror_to_tag_id=tag.id)
    _as("operator", uid=7)
    await client.post("/api/lab/samples", json={
        "sample_point_id": point.id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [{"parameter_id": ph.id, "value": 7.4}],
    })
    rows = (await db_session.execute(select(TagReading).where(TagReading.tag_id == tag.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == 7.4


@pytest.mark.asyncio
async def test_no_mirror_when_unset(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH")  # mirror_to_tag_id None
    _as("operator", uid=7)
    await client.post("/api/lab/samples", json={
        "sample_point_id": point.id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [{"parameter_id": ph.id, "value": 7.4}],
    })
    rows = (await db_session.execute(select(TagReading))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_batch_insert(client, db_session):
    point = await _seed_point(db_session)
    ph = await _seed_param(db_session, code="PH")
    _as("operator", uid=7)
    resp = await client.post("/api/lab/samples/batch", json={"rows": [
        {"sample_point_id": point.id, "sampled_at": "2026-06-27T09:00:00",
         "measurements": [{"parameter_id": ph.id, "value": 7.1}]},
        {"sample_point_id": point.id, "sampled_at": "2026-06-27T12:00:00",
         "measurements": [{"parameter_id": ph.id, "value": 7.3}]},
    ]})
    assert resp.status_code == 201, resp.text
    assert resp.json()["inserted"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_samples.py -p no:randomly -n0 -v`
Expected: FAIL — 404 (endpoints missing).

- [ ] **Step 3: Add sample endpoints to the router**

Append to `scada-reporter/backend/app/api/lab.py` (add imports `from datetime import datetime`, `from app.models.lab import LabMeasurement, LabSample`, `from app.models.tag import TagReading` at the top):

```python
class MeasurementIn(BaseModel):
    parameter_id: int
    value: float | None = None
    text_value: str | None = None


class SampleCreate(BaseModel):
    sample_point_id: int
    sampled_at: datetime
    method: str = ""
    batch_no: str = ""
    note: str = ""
    measurements: list[MeasurementIn] = []


class MeasurementOut(BaseModel):
    id: int
    parameter_id: int
    value: float | None
    text_value: str | None
    flag: str | None
    model_config = {"from_attributes": True}


class SampleOut(BaseModel):
    id: int
    sample_point_id: int
    sampled_at: datetime
    entered_by: int
    method: str
    batch_no: str
    note: str
    measurements: list[MeasurementOut]
    model_config = {"from_attributes": True}


def compute_flag(
    value: float | None, min_limit: float | None, max_limit: float | None
) -> str | None:
    if value is None:
        return None
    if min_limit is not None and value < min_limit:
        return "over_limit"
    if max_limit is not None and value > max_limit:
        return "over_limit"
    return None


async def _build_sample(db: AsyncSession, data: SampleCreate, entered_by: int) -> LabSample:
    """Create a LabSample + its measurements (with flag + mirror) in the session.

    Does NOT commit — caller owns the transaction boundary.
    """
    sample = LabSample(
        sample_point_id=data.sample_point_id,
        sampled_at=data.sampled_at,
        entered_by=entered_by,
        method=data.method,
        batch_no=data.batch_no,
        note=data.note,
    )
    db.add(sample)
    await db.flush()  # sample.id

    # preload referenced parameters for limits + mirror target
    param_ids = [m.parameter_id for m in data.measurements]
    params = {}
    if param_ids:
        rows = await db.execute(select(LabParameter).where(LabParameter.id.in_(param_ids)))
        params = {p.id: p for p in rows.scalars().all()}

    for m in data.measurements:
        param = params.get(m.parameter_id)
        if param is None:
            raise HTTPException(status_code=400, detail=f"Parametre yok: {m.parameter_id}")
        flag = compute_flag(m.value, param.min_limit, param.max_limit)
        db.add(
            LabMeasurement(
                sample_id=sample.id,
                parameter_id=m.parameter_id,
                value=m.value,
                text_value=m.text_value,
                flag=flag,
            )
        )
        if param.mirror_to_tag_id is not None and m.value is not None:
            db.add(
                TagReading(
                    tag_id=param.mirror_to_tag_id,
                    value=m.value,
                    quality=192,
                    timestamp=data.sampled_at,
                )
            )
    return sample


@router.post("/samples", response_model=SampleOut, status_code=201)
async def create_sample(
    data: SampleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _build_sample(db, data, entered_by=user.id)
    await db.commit()
    await db.refresh(sample, attribute_names=["measurements"])
    return sample


class BatchCreate(BaseModel):
    rows: list[SampleCreate]


@router.post("/samples/batch", status_code=201)
async def create_samples_batch(
    data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    ids = []
    for row in data.rows:
        sample = await _build_sample(db, row, entered_by=user.id)
        await db.flush()
        ids.append(sample.id)
    await db.commit()
    return {"inserted": len(ids), "sample_ids": ids}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_samples.py -p no:randomly -n0 -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/lab.py scada-reporter/backend/tests/test_lab_samples.py
git commit -m "feat(lab): sample entry (single + batch) with limit flag + tag_readings mirror"
```

---

## Task 4: List / get / edit / delete with ownership + audit

**Files:**
- Modify: `scada-reporter/backend/app/api/lab.py`
- Test: `scada-reporter/backend/tests/test_lab_edit_delete.py`

**Interfaces:**
- Consumes: Task 3 schemas/helpers; `record_audit` from `app.core.audit`.
- Produces:
  - `GET /lab/samples?point_id=&parameter_id=&start=&end=&entered_by=&limit=&offset=` → `list[SampleOut]`
  - `GET /lab/samples/{id}` → `SampleOut`
  - `PATCH /lab/samples/{id}` (admin or owner) — body `SampleCreate` (full replace of measurements) → `SampleOut`; writes audit `lab.sample.update`
  - `DELETE /lab/samples/{id}` (admin or owner) → 204; writes audit `lab.sample.delete`
  - helper `_assert_can_edit(user, sample)`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_edit_delete.py`:

```python
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.audit_log import AuditLog
from app.models.lab import LabParameter, LabSample, LabSamplePoint


def _as(role: str, uid: int):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def _seed(db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH")
    db_session.add_all([point, param])
    await db_session.commit()
    await db_session.refresh(point)
    await db_session.refresh(param)
    return point, param


async def _make_sample(client, point_id, param_id):
    return (await client.post("/api/lab/samples", json={
        "sample_point_id": point_id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [{"parameter_id": param_id, "value": 7.0}],
    })).json()


@pytest.mark.asyncio
async def test_owner_can_delete_own_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 204
    rows = (await db_session.execute(select(AuditLog).where(AuditLog.action == "lab.sample.delete"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_operator_cannot_delete_others_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    _as("operator", uid=99)  # different operator
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_any_sample(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    _as("admin", uid=1)
    resp = await client.delete(f"/api/lab/samples/{s['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_owner_can_edit_and_audit_written(client, db_session):
    point, param = await _seed(db_session)
    _as("operator", uid=7)
    s = await _make_sample(client, point.id, param.id)
    resp = await client.patch(f"/api/lab/samples/{s['id']}", json={
        "sample_point_id": point.id,
        "sampled_at": "2026-06-27T09:00:00",
        "measurements": [{"parameter_id": param.id, "value": 8.5}],
    })
    assert resp.status_code == 200
    assert resp.json()["measurements"][0]["value"] == 8.5
    rows = (await db_session.execute(select(AuditLog).where(AuditLog.action == "lab.sample.update"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_filters_by_point(client, db_session):
    point, param = await _seed(db_session)
    other = LabSamplePoint(code="OUT", name="Out")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    _as("operator", uid=7)
    await _make_sample(client, point.id, param.id)
    await _make_sample(client, other.id, param.id)
    resp = await client.get(f"/api/lab/samples?point_id={point.id}")
    assert resp.status_code == 200
    assert all(s["sample_point_id"] == point.id for s in resp.json())
    assert len(resp.json()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_edit_delete.py -p no:randomly -n0 -v`
Expected: FAIL — 404/405 (endpoints missing).

- [ ] **Step 3: Add list/get/edit/delete endpoints**

Append to `scada-reporter/backend/app/api/lab.py` (add imports `from datetime import datetime` already present; add `from fastapi import Request`; `from sqlalchemy import and_`; `from app.core.audit import record_audit`; `from app.models.lab import LabMeasurement` already imported):

```python
def _assert_can_edit(user: User, sample: LabSample) -> None:
    if user.role != "admin" and sample.entered_by != user.id:
        raise HTTPException(status_code=403, detail="Yalnizca kendi kaydinizi duzenleyebilirsiniz")


@router.get("/samples", response_model=list[SampleOut])
async def list_samples(
    point_id: int | None = Query(default=None),
    parameter_id: int | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    entered_by: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    conditions = []
    if point_id is not None:
        conditions.append(LabSample.sample_point_id == point_id)
    if start is not None:
        conditions.append(LabSample.sampled_at >= start)
    if end is not None:
        conditions.append(LabSample.sampled_at <= end)
    if entered_by is not None:
        conditions.append(LabSample.entered_by == entered_by)
    query = select(LabSample)
    if parameter_id is not None:
        query = query.join(LabMeasurement).where(LabMeasurement.parameter_id == parameter_id)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(LabSample.sampled_at.desc()).limit(limit).offset(offset).distinct()
    samples = (await db.execute(query)).scalars().unique().all()
    # eager-load measurements
    for s in samples:
        await db.refresh(s, attribute_names=["measurements"])
    return samples


async def _get_sample_or_404(db: AsyncSession, sample_id: int) -> LabSample:
    sample = (
        await db.execute(select(LabSample).where(LabSample.id == sample_id))
    ).scalar_one_or_none()
    if not sample:
        raise HTTPException(status_code=404, detail="Numune bulunamadi")
    await db.refresh(sample, attribute_names=["measurements"])
    return sample


@router.get("/samples/{sample_id}", response_model=SampleOut)
async def get_sample(
    sample_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await _get_sample_or_404(db, sample_id)


@router.patch("/samples/{sample_id}", response_model=SampleOut)
async def update_sample(
    sample_id: int,
    data: SampleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _get_sample_or_404(db, sample_id)
    _assert_can_edit(user, sample)
    # Update scalar fields
    sample.sample_point_id = data.sample_point_id
    sample.sampled_at = data.sampled_at
    sample.method = data.method
    sample.batch_no = data.batch_no
    sample.note = data.note
    # Full replace of measurements (clears + rebuilds; mirror not re-applied on edit)
    for existing in list(sample.measurements):
        await db.delete(existing)
    await db.flush()
    param_ids = [m.parameter_id for m in data.measurements]
    params = {}
    if param_ids:
        rows = await db.execute(select(LabParameter).where(LabParameter.id.in_(param_ids)))
        params = {p.id: p for p in rows.scalars().all()}
    for m in data.measurements:
        param = params.get(m.parameter_id)
        if param is None:
            raise HTTPException(status_code=400, detail=f"Parametre yok: {m.parameter_id}")
        db.add(
            LabMeasurement(
                sample_id=sample.id,
                parameter_id=m.parameter_id,
                value=m.value,
                text_value=m.text_value,
                flag=compute_flag(m.value, param.min_limit, param.max_limit),
            )
        )
    await record_audit(
        db,
        actor=user,
        action="lab.sample.update",
        target_type="lab_sample",
        target_id=sample.id,
        detail={"sample_point_id": data.sample_point_id, "n_measurements": len(data.measurements)},
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(sample, attribute_names=["measurements"])
    return sample


@router.delete("/samples/{sample_id}", status_code=204)
async def delete_sample(
    sample_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    sample = await _get_sample_or_404(db, sample_id)
    _assert_can_edit(user, sample)
    await record_audit(
        db,
        actor=user,
        action="lab.sample.delete",
        target_type="lab_sample",
        target_id=sample.id,
        detail={"sample_point_id": sample.sample_point_id},
        ip=request.client.host if request.client else None,
    )
    await db.delete(sample)
    await db.commit()
```

> NOTE: `FastAPI` requires the non-default `request: Request` parameter to precede parameters with `Depends(...)` defaults only if you give it no default — it has none here, so place it before the `db=Depends(...)` args as shown. This matches `auth.register`'s signature style.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_edit_delete.py -p no:randomly -n0 -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/app/api/lab.py scada-reporter/backend/tests/test_lab_edit_delete.py
git commit -m "feat(lab): list/get/edit/delete with ownership guard + audit"
```

---

## Task 5: Excel/CSV import (preview + commit)

**Files:**
- Create: `scada-reporter/backend/app/services/lab_import.py`
- Modify: `scada-reporter/backend/app/api/lab.py`
- Test: `scada-reporter/backend/tests/test_lab_import.py`

**Interfaces:**
- Consumes: Task 3 `_build_sample`, Task 1 models.
- Produces:
  - service `parse_table(content: bytes, filename: str) -> tuple[list[str], list[list[str]]]` returning `(headers, rows)` for `.csv`/`.xlsx`.
  - `POST /lab/import/preview` (multipart `file`) → `{headers: list[str], rows: list[list[str]], suggestions: dict[str, int|None]}` where suggestions maps a header to a matching parameter id (by code/name, case-insensitive) or None.
  - `POST /lab/import/commit` (JSON `{sample_point_id, time_column, mapping: dict[str,int], rows: list[list[str]], headers: list[str]}`) → `{inserted: int, errors: list[str]}`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_import.py`:

```python
import io
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.api.auth import get_current_user
from app.main import app
from app.models.lab import LabParameter, LabSample, LabSamplePoint


def _as(role: str, uid: int = 7):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_preview_suggests_mapping(client, db_session):
    db_session.add(LabParameter(code="PH", name="pH"))
    await db_session.commit()
    _as("operator")
    content = _xlsx([["time", "pH"], ["2026-06-27T09:00:00", "7.2"]])
    resp = await client.post(
        "/api/lab/import/preview",
        files={"file": ("lab.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["headers"] == ["time", "pH"]
    # "pH" header maps to the PH parameter
    ph = (await db_session.execute(select(LabParameter))).scalars().first()
    assert body["suggestions"]["pH"] == ph.id
    assert body["suggestions"]["time"] is None


@pytest.mark.asyncio
async def test_commit_imports_rows(client, db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH")
    db_session.add_all([point, param])
    await db_session.commit()
    await db_session.refresh(point)
    await db_session.refresh(param)
    _as("operator")
    resp = await client.post("/api/lab/import/commit", json={
        "sample_point_id": point.id,
        "time_column": "time",
        "headers": ["time", "pH"],
        "mapping": {"pH": param.id},
        "rows": [
            ["2026-06-27T09:00:00", "7.2"],
            ["2026-06-27T12:00:00", "7.4"],
            ["bad-date", "9.9"],
        ],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 2
    assert len(body["errors"]) == 1
    samples = (await db_session.execute(select(LabSample))).scalars().all()
    assert len(samples) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_import.py -p no:randomly -n0 -v`
Expected: FAIL — module/endpoint missing.

- [ ] **Step 3: Write the import service**

Create `scada-reporter/backend/app/services/lab_import.py`:

```python
import csv
import io


def parse_table(content: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    """Parse a CSV or XLSX upload into (headers, rows-of-strings).

    Empty trailing cells are normalized to "". The first row is the header.
    """
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(text)))
        if not reader:
            return [], []
        headers = [h.strip() for h in reader[0]]
        rows = [[(c or "").strip() for c in r] for r in reader[1:] if any(c.strip() for c in r)]
        return headers, rows
    if name.endswith((".xlsx", ".xls")):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        all_rows = [
            [("" if c is None else str(c)).strip() for c in row]
            for row in ws.iter_rows(values_only=True)
        ]
        if not all_rows:
            return [], []
        headers = all_rows[0]
        rows = [r for r in all_rows[1:] if any(c for c in r)]
        return headers, rows
    raise ValueError("Desteklenmeyen dosya turu (.csv veya .xlsx)")
```

- [ ] **Step 4: Add import endpoints to the router**

Append to `scada-reporter/backend/app/api/lab.py` (add imports `from fastapi import UploadFile`; `from app.services.lab_import import parse_table`):

```python
@router.post("/import/preview")
async def import_preview(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    content = await file.read()
    try:
        headers, rows = parse_table(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Suggest a parameter per header by case-insensitive code/name match.
    params = (await db.execute(select(LabParameter))).scalars().all()
    by_code = {p.code.lower(): p.id for p in params}
    by_name = {p.name.lower(): p.id for p in params}
    suggestions: dict[str, int | None] = {}
    for h in headers:
        key = h.lower()
        suggestions[h] = by_code.get(key) or by_name.get(key)
    return {"headers": headers, "rows": rows[:200], "suggestions": suggestions}


class ImportCommit(BaseModel):
    sample_point_id: int
    time_column: str
    headers: list[str]
    mapping: dict[str, int]  # header -> parameter_id
    rows: list[list[str]]


@router.post("/import/commit")
async def import_commit(
    data: ImportCommit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
    _w=Depends(require_writable),
):
    try:
        time_idx = data.headers.index(data.time_column)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Zaman kolonu basliklarda yok") from e
    col_index = {h: i for i, h in enumerate(data.headers)}
    inserted, errors = 0, []
    for row_no, row in enumerate(data.rows, start=2):
        raw_time = row[time_idx] if time_idx < len(row) else ""
        try:
            sampled_at = datetime.fromisoformat(raw_time)
        except ValueError:
            errors.append(f"satir {row_no}: gecersiz tarih ({raw_time})")
            continue
        measurements = []
        for header, param_id in data.mapping.items():
            idx = col_index.get(header)
            if idx is None or idx >= len(row) or row[idx] == "":
                continue
            try:
                value = float(row[idx])
            except ValueError:
                errors.append(f"satir {row_no}: {header} sayi degil ({row[idx]})")
                continue
            measurements.append(MeasurementIn(parameter_id=param_id, value=value))
        if not measurements:
            continue
        await _build_sample(
            db,
            SampleCreate(
                sample_point_id=data.sample_point_id,
                sampled_at=sampled_at,
                measurements=measurements,
            ),
            entered_by=user.id,
        )
        inserted += 1
    await db.commit()
    return {"inserted": inserted, "errors": errors}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_lab_import.py -p no:randomly -n0 -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full lab backend suite + checks**

Run: `.venv/Scripts/python -m pytest tests/test_lab_*.py -n0 -v` then `just check`
Expected: all lab tests pass; ruff + mypy clean.

- [ ] **Step 7: Commit**

```bash
git add scada-reporter/backend/app/services/lab_import.py scada-reporter/backend/app/api/lab.py scada-reporter/backend/tests/test_lab_import.py
git commit -m "feat(lab): Excel/CSV import preview + commit"
```

---

## Task 6: Grafana view test + provisioned dashboard

**Files:**
- Create: `scada-reporter/backend/tests/test_lab_view.py`
- Create: `scada-reporter/docker/grafana/dashboards/lab-quality.json`
- Test: `scada-reporter/backend/tests/test_lab_view.py`

**Interfaces:**
- Consumes: the `v_lab_timeseries` view from Task 1's migration. NOTE: the conftest builds the schema with `Base.metadata.create_all`, which does NOT create the view (views aren't ORM tables). The test therefore creates the view itself from the same SQL, asserting the SELECT shape is valid and portable to SQLite.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_lab_view.py`:

```python
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint

_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_lab_timeseries AS
SELECT ls.sampled_at AS time, sp.code AS point_code, lp.code AS param_code,
       lp.name AS param_name, lp.unit AS unit, lm.value AS value,
       lp.min_limit AS min_limit, lp.max_limit AS max_limit
FROM lab_measurements lm
JOIN lab_samples ls ON ls.id = lm.sample_id
JOIN lab_parameters lp ON lp.id = lm.parameter_id
JOIN lab_sample_points sp ON sp.id = ls.sample_point_id
WHERE lm.value IS NOT NULL
"""


@pytest.mark.asyncio
async def test_view_returns_flattened_timeseries(db_session):
    point = LabSamplePoint(code="INLET", name="Inlet")
    param = LabParameter(code="PH", name="pH", unit="", max_limit=9.0)
    db_session.add_all([point, param])
    await db_session.flush()
    sample = LabSample(sample_point_id=point.id, sampled_at=datetime(2026, 6, 27, 9, 0), entered_by=1)
    db_session.add(sample)
    await db_session.flush()
    db_session.add(LabMeasurement(sample_id=sample.id, parameter_id=param.id, value=7.2))
    await db_session.commit()

    await db_session.execute(text(_VIEW_SQL))
    rows = (await db_session.execute(text(
        "SELECT point_code, param_code, value, max_limit FROM v_lab_timeseries"
    ))).all()
    assert len(rows) == 1
    assert rows[0].point_code == "INLET"
    assert rows[0].param_code == "PH"
    assert rows[0].value == 7.2
    assert rows[0].max_limit == 9.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_lab_view.py -p no:randomly -n0 -v`
Expected: PASS already? No — it should PASS once the models exist (Task 1 done). If models/columns mismatch the SQL, it FAILS. Treat a failure here as a column-name mismatch to fix in the view SQL (Task 1 migration AND this test must agree).

> This task's "test-first" value is verifying the view SELECT is portable and column names match the model. If it passes immediately, that confirms Task 1's view SQL is correct; proceed to the dashboard.

- [ ] **Step 3: Create the provisioned dashboard**

Create `scada-reporter/docker/grafana/dashboards/lab-quality.json` (Grafana schema, TimescaleDB datasource uid `timescaledb`, template variables for point + parameter):

```json
{
  "annotations": { "list": [] },
  "editable": true,
  "schemaVersion": 39,
  "title": "Lab Quality",
  "uid": "lab-quality",
  "tags": ["lab"],
  "templating": {
    "list": [
      {
        "name": "point",
        "label": "Sample Point",
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "query": "SELECT DISTINCT point_code FROM v_lab_timeseries ORDER BY 1",
        "type": "query",
        "includeAll": true,
        "multi": true
      },
      {
        "name": "param",
        "label": "Parameter",
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "query": "SELECT DISTINCT param_code FROM v_lab_timeseries ORDER BY 1",
        "type": "query",
        "includeAll": true,
        "multi": true
      }
    ]
  },
  "time": { "from": "now-30d", "to": "now" },
  "panels": [
    {
      "type": "timeseries",
      "title": "Lab measurements over time",
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "gridPos": { "h": 10, "w": 24, "x": 0, "y": 0 },
      "targets": [
        {
          "format": "time_series",
          "rawSql": "SELECT time AS \"time\", param_code AS metric, value FROM v_lab_timeseries WHERE point_code IN (${point:sqlstring}) AND param_code IN (${param:sqlstring}) AND $__timeFilter(time) ORDER BY time",
          "rawQuery": true
        }
      ]
    },
    {
      "type": "table",
      "title": "Latest values",
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "gridPos": { "h": 10, "w": 24, "x": 0, "y": 10 },
      "targets": [
        {
          "format": "table",
          "rawSql": "SELECT time, point_code, param_name, value, unit, min_limit, max_limit FROM v_lab_timeseries WHERE point_code IN (${point:sqlstring}) AND param_code IN (${param:sqlstring}) AND $__timeFilter(time) ORDER BY time DESC LIMIT 200",
          "rawQuery": true
        }
      ]
    }
  ]
}
```

- [ ] **Step 4: Validate the dashboard JSON**

Run: `.venv/Scripts/python -c "import json; json.load(open('../docker/grafana/dashboards/lab-quality.json'))"`
(from `scada-reporter/backend`; adjust path or run `python -c "import json,glob;[json.load(open(f)) for f in glob.glob('scada-reporter/docker/grafana/dashboards/*.json')]"` from repo root)
Expected: no output = valid JSON. `configure-grafana-windows-service.ps1` already copies `*.json` into the service provisioning folder, so no script change is needed.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/backend/tests/test_lab_view.py scada-reporter/docker/grafana/dashboards/lab-quality.json
git commit -m "feat(lab): v_lab_timeseries view test + provisioned Grafana dashboard"
```

---

## Task 7: Frontend — Lab Entry page (Single Sample tab) + i18n + nav + client

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts` (regenerated — do not hand-edit)
- Create: `scada-reporter/frontend/src/i18n/locales/{en,tr,ru,de,ar}/lab.json`
- Modify: `scada-reporter/frontend/src/i18n/index.ts`
- Create: `scada-reporter/frontend/src/pages/LabEntry.tsx`
- Create: `scada-reporter/frontend/src/pages/lab/SingleSampleTab.tsx`
- Modify: `scada-reporter/frontend/src/components/Layout.tsx` (sidebar item)
- Modify: `scada-reporter/frontend/src/App.tsx` (route)
- Test: `scada-reporter/frontend/src/pages/lab/SingleSampleTab.test.tsx`

**Interfaces:**
- Consumes: generated client functions for `/api/lab/*` (after `just gen-client`).
- Produces: `LabEntry` default-export page mounted at `/lab`; sidebar link "Lab Data Entry".

- [ ] **Step 1: Regenerate the API client**

With the backend running (`just run-backend`), run: `just gen-client`
Expected: `src/api/client.ts` gains `createSample`, `listLabParameters`, `listLabSamplePoints`, etc. Verify: `grep -c "lab" scada-reporter/frontend/src/api/client.ts` returns > 0.

- [ ] **Step 2: Add the i18n namespace (all 5 languages)**

Create `scada-reporter/frontend/src/i18n/locales/en/lab.json`:

```json
{
  "title": "Lab Data Entry",
  "subtitle": "Enter laboratory analysis and measurement results",
  "tab_single": "Single Sample",
  "tab_batch": "Batch Table",
  "tab_import": "Import",
  "tab_records": "Records",
  "sample_point": "Sample Point",
  "sampled_at": "Date / Time",
  "method": "Method",
  "batch_no": "Batch No",
  "note": "Note",
  "add_parameter": "+ new parameter",
  "add_point": "+ new point",
  "save": "Save",
  "saved": "Saved",
  "out_of_range": "Out of range",
  "value": "Value"
}
```

Create the same keys translated for `tr`, `ru`, `de`, `ar` (Turkish example):

```json
{
  "title": "Lab Veri Girişi",
  "subtitle": "Laboratuvar analiz ve ölçüm sonuçlarını girin",
  "tab_single": "Tekil Numune",
  "tab_batch": "Toplu Tablo",
  "tab_import": "İçe Aktar",
  "tab_records": "Kayıtlar",
  "sample_point": "Numune Noktası",
  "sampled_at": "Tarih / Saat",
  "method": "Yöntem",
  "batch_no": "Parti No",
  "note": "Not",
  "add_parameter": "+ yeni parametre",
  "add_point": "+ yeni nokta",
  "save": "Kaydet",
  "saved": "Kaydedildi",
  "out_of_range": "Limit dışı",
  "value": "Değer"
}
```

(Provide `ru`, `de`, `ar` files with the same keys — translate the values; reuse an existing locale folder's style. For `ar`, values in Arabic.)

In `scada-reporter/frontend/src/i18n/index.ts`, register `lab` in THREE places per the existing pattern: (1) import each `lab.json`, (2) add `lab` to each language's `resources` object, (3) add `"lab"` to the `ns` array. Match exactly how an existing namespace (e.g. `grafana`) is wired — open the file and copy that triple.

- [ ] **Step 3: Write the failing component test**

Create `scada-reporter/frontend/src/pages/lab/SingleSampleTab.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { isOutOfRange } from './SingleSampleTab'

describe('isOutOfRange', () => {
  it('returns false when within limits', () => {
    expect(isOutOfRange(7.2, 6.5, 9.0)).toBe(false)
  })
  it('returns true below min', () => {
    expect(isOutOfRange(5.0, 6.5, 9.0)).toBe(true)
  })
  it('returns true above max', () => {
    expect(isOutOfRange(9.9, 6.5, 9.0)).toBe(true)
  })
  it('returns false when limits are null', () => {
    expect(isOutOfRange(123, null, null)).toBe(false)
  })
  it('returns false for empty value', () => {
    expect(isOutOfRange(null, 6.5, 9.0)).toBe(false)
  })
})
```

- [ ] **Step 4: Run test to verify it fails**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/lab/SingleSampleTab.test.tsx`
Expected: FAIL — cannot resolve `./SingleSampleTab`.

- [ ] **Step 5: Write the Single Sample tab (with the tested pure helper)**

Create `scada-reporter/frontend/src/pages/lab/SingleSampleTab.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createSample,
  listLabParameters,
  listLabSamplePoints,
  type LabParameterOut,
  type LabSamplePointOut,
} from '../../api/client'

// Pure, unit-tested: a value is out of range when below min or above max.
export function isOutOfRange(
  value: number | null,
  min: number | null,
  max: number | null,
): boolean {
  if (value === null || Number.isNaN(value)) return false
  if (min !== null && value < min) return true
  if (max !== null && value > max) return true
  return false
}

export default function SingleSampleTab() {
  const { t } = useTranslation('lab')
  const [points, setPoints] = useState<LabSamplePointOut[]>([])
  const [params, setParams] = useState<LabParameterOut[]>([])
  const [pointId, setPointId] = useState<number | ''>('')
  const [sampledAt, setSampledAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [values, setValues] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([listLabSamplePoints({ query: { approved: true } }), listLabParameters({ query: { approved: true } })])
      .then(([pts, prs]) => {
        setPoints(pts.data ?? [])
        setParams(prs.data ?? [])
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const handleSave = async () => {
    if (pointId === '') return
    setSaving(true)
    setSaved(false)
    setError(null)
    const measurements = Object.entries(values)
      .filter(([, v]) => v !== '')
      .map(([pid, v]) => ({ parameter_id: Number(pid), value: Number(v) }))
    try {
      await createSample({
        body: { sample_point_id: Number(pointId), sampled_at: new Date(sampledAt).toISOString(), measurements },
      })
      setSaved(true)
      setValues({})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sample_point')}</span>
          <select
            value={pointId}
            onChange={(e) => setPointId(e.target.value === '' ? '' : Number(e.target.value))}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          >
            <option value="">—</option>
            {points.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-xs uppercase text-gray-500">{t('sampled_at')}</span>
          <input
            type="datetime-local"
            value={sampledAt}
            onChange={(e) => setSampledAt(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
          />
        </label>
      </div>

      <div className="space-y-2">
        {params.map((param) => {
          const raw = values[param.id] ?? ''
          const num = raw === '' ? null : Number(raw)
          const bad = isOutOfRange(num, param.min_limit, param.max_limit)
          return (
            <div key={param.id} className="flex items-center gap-3">
              <span className="w-40 text-sm text-gray-300">
                {param.name} {param.unit ? `(${param.unit})` : ''}
              </span>
              <input
                value={raw}
                onChange={(e) => setValues((v) => ({ ...v, [param.id]: e.target.value }))}
                className={`w-32 rounded-lg border bg-gray-900 px-3 py-2 text-sm text-gray-100 ${bad ? 'border-red-500' : 'border-gray-700'}`}
              />
              {bad && <span className="text-xs text-red-400">{t('out_of_range')}</span>}
            </div>
          )
        })}
      </div>

      <button
        onClick={handleSave}
        disabled={saving || pointId === ''}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-gray-700"
      >
        {saving ? '…' : t('save')}
      </button>
      {saved && <span className="ml-3 text-sm text-green-400">{t('saved')}</span>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  )
}
```

> NOTE: the exact generated function signatures (`createSample`, `listLabParameters`, return-shape `.data`, `query`/`body` wrappers) depend on `openapi-ts` output. Open `src/api/client.ts` after Step 1 and adjust call sites to match the real generated names/shapes (the project uses `@hey-api/openapi-ts`-style `{ body }`/`{ query }` wrappers — confirm against an existing page like `Grafana.tsx`'s `generateGrafanaDashboard` usage).

- [ ] **Step 6: Write the LabEntry shell + route + sidebar**

Create `scada-reporter/frontend/src/pages/LabEntry.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import SingleSampleTab from './lab/SingleSampleTab'

type TabKey = 'single' | 'batch' | 'import' | 'records'

export default function LabEntry() {
  const { t } = useTranslation('lab')
  const [tab, setTab] = useState<TabKey>('single')
  const tabs: { key: TabKey; label: string }[] = [
    { key: 'single', label: t('tab_single') },
    { key: 'batch', label: t('tab_batch') },
    { key: 'import', label: t('tab_import') },
    { key: 'records', label: t('tab_records') },
  ]
  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">{t('title')}</h1>
        <p className="text-sm text-gray-500">{t('subtitle')}</p>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-gray-800 pb-3">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`rounded-lg px-4 py-2 text-sm transition-colors ${tab === tb.key ? 'bg-blue-600 text-white' : 'bg-gray-900 text-gray-400 hover:bg-gray-800'}`}
          >
            {tb.label}
          </button>
        ))}
      </div>
      {tab === 'single' && <SingleSampleTab />}
      {tab !== 'single' && <p className="text-sm text-gray-500">…</p>}
    </div>
  )
}
```

In `scada-reporter/frontend/src/App.tsx`, add the route alongside the others (match existing lazy/Route pattern):

```tsx
<Route path="/lab" element={<LabEntry />} />
```
…with `import LabEntry from './pages/LabEntry'` at the top (follow whatever import style the file uses).

In `scada-reporter/frontend/src/components/Layout.tsx`, add a sidebar nav item next to the existing ones (e.g. near the "Monitoring & Analytics"/Grafana link), label from `t('lab:title')` or the nav namespace the file uses:

```tsx
<NavLink to="/lab" className={navClass}>{t('lab:title')}</NavLink>
```
Match the exact `NavLink`/icon/class pattern already in `Layout.tsx`.

- [ ] **Step 7: Run the component test + typecheck**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/lab/SingleSampleTab.test.tsx` then `pnpm tsc -b`
Expected: 5 tests pass; `tsc -b` reports 0 errors.

- [ ] **Step 8: Commit**

```bash
git add scada-reporter/frontend/src/api/client.ts scada-reporter/frontend/src/i18n scada-reporter/frontend/src/pages/LabEntry.tsx scada-reporter/frontend/src/pages/lab scada-reporter/frontend/src/components/Layout.tsx scada-reporter/frontend/src/App.tsx
git commit -m "feat(lab): frontend Lab Entry page (single sample) + i18n + nav"
```

---

## Task 8: Frontend — Batch, Import, Records tabs + Settings catalog card

**Files:**
- Create: `scada-reporter/frontend/src/pages/lab/BatchTab.tsx`
- Create: `scada-reporter/frontend/src/pages/lab/ImportTab.tsx`
- Create: `scada-reporter/frontend/src/pages/lab/RecordsTab.tsx`
- Create: `scada-reporter/frontend/src/pages/lab/LabCatalogCard.tsx`
- Modify: `scada-reporter/frontend/src/pages/LabEntry.tsx` (wire the 3 tabs)
- Modify: `scada-reporter/frontend/src/pages/Settings.tsx` (mount catalog card)
- Test: `scada-reporter/frontend/src/pages/lab/RecordsTab.test.tsx`

**Interfaces:**
- Consumes: Task 7 client functions + `createSamplesBatch`, `importPreview`, `importCommit`, `listSamples`, `deleteSample`, `updateSample`, catalog CRUD.
- Produces: fully wired four-tab page + admin catalog card.

- [ ] **Step 1: Write the failing test (Records ownership helper)**

Create `scada-reporter/frontend/src/pages/lab/RecordsTab.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { canEditRecord } from './RecordsTab'

describe('canEditRecord', () => {
  it('admin can edit any record', () => {
    expect(canEditRecord({ role: 'admin', id: 1 }, 999)).toBe(true)
  })
  it('operator can edit own record', () => {
    expect(canEditRecord({ role: 'operator', id: 7 }, 7)).toBe(true)
  })
  it('operator cannot edit others record', () => {
    expect(canEditRecord({ role: 'operator', id: 7 }, 8)).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/pages/lab/RecordsTab.test.tsx`
Expected: FAIL — cannot resolve `./RecordsTab`.

- [ ] **Step 3: Implement the three tabs + catalog card**

Create `scada-reporter/frontend/src/pages/lab/RecordsTab.tsx` exporting the tested helper plus the records list:

```tsx
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteSample, listSamples, type SampleOut } from '../../api/client'
import { useAuth } from '../../context/AuthContext'

export function canEditRecord(
  user: { role: string; id: number },
  enteredBy: number,
): boolean {
  return user.role === 'admin' || user.id === enteredBy
}

export default function RecordsTab() {
  const { t } = useTranslation('lab')
  const { user } = useAuth()
  const [samples, setSamples] = useState<SampleOut[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = () =>
    listSamples({ query: { limit: 100 } })
      .then((r) => setSamples(r.data ?? []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))

  useEffect(() => {
    reload()
  }, [])

  const onDelete = async (id: number) => {
    await deleteSample({ path: { sample_id: id } })
    await reload()
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-red-400">{error}</p>}
      <table className="w-full text-sm text-gray-200">
        <thead className="text-gray-500">
          <tr>
            <th className="text-start">{t('sampled_at')}</th>
            <th className="text-start">{t('sample_point')}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {samples.map((s) => (
            <tr key={s.id} className="border-t border-gray-800">
              <td>{new Date(s.sampled_at).toLocaleString()}</td>
              <td>{s.sample_point_id}</td>
              <td className="text-end">
                {user && canEditRecord({ role: user.role, id: user.id }, s.entered_by) && (
                  <button onClick={() => onDelete(s.id)} className="text-red-400 hover:underline">
                    ✕
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

> NOTE: confirm `useAuth()` exposes `user.role` and `user.id` (open `src/context/AuthContext.tsx`). If the shape differs, adapt `canEditRecord`'s call site (keep the pure helper signature so the test stays valid).

Create `BatchTab.tsx` (grid: rows of {time, values per chosen parameter column} → one `createSamplesBatch` call), `ImportTab.tsx` (file input → `importPreview` → mapping selects → `importCommit`, show `{inserted, errors}`), and `LabCatalogCard.tsx` (admin: parameter/point lists with create form + a "pending approval" section listing `approved=false` with an Approve button calling the PATCH). Follow the same styling and client-call patterns established in Task 7 and `SingleSampleTab.tsx`. Each is self-contained and consumes only the generated client + i18n.

Wire the three tabs into `LabEntry.tsx`:

```tsx
import BatchTab from './lab/BatchTab'
import ImportTab from './lab/ImportTab'
import RecordsTab from './lab/RecordsTab'
// …replace the placeholder block:
{tab === 'single' && <SingleSampleTab />}
{tab === 'batch' && <BatchTab />}
{tab === 'import' && <ImportTab />}
{tab === 'records' && <RecordsTab />}
```

Mount `LabCatalogCard` in `src/pages/Settings.tsx` behind an admin check (follow the existing pattern Settings uses for admin-only cards, e.g. the License card):

```tsx
{user?.role === 'admin' && <LabCatalogCard />}
```

- [ ] **Step 4: Run the test + typecheck + lint**

Run (from `scada-reporter/frontend`): `pnpm vitest run src/pages/lab/RecordsTab.test.tsx` then `pnpm tsc -b` then `pnpm lint`
Expected: 3 tests pass; `tsc -b` 0 errors; lint clean.

- [ ] **Step 5: Commit**

```bash
git add scada-reporter/frontend/src/pages/lab scada-reporter/frontend/src/pages/LabEntry.tsx scada-reporter/frontend/src/pages/Settings.tsx
git commit -m "feat(lab): batch, import, records tabs + admin catalog card"
```

---

## Task 9: End-to-end verification + docs

**Files:**
- Create: `scada-reporter/docs/lab-data-entry.md` (or `docs/lab-data-entry.md` — match where existing feature docs live; the repo uses top-level `docs/` for guides like `grafana-windows-service.md`)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full backend suite**

Run (from `scada-reporter/backend`): `just test`
Expected: all tests pass (existing + new lab tests), parallel + randomized.

- [ ] **Step 2: Run all checks**

Run (from repo root): `just check`
Expected: ruff + mypy + frontend lint/build all green.

- [ ] **Step 3: Manual E2E (browser)**

With `just dev` running and Grafana up:
1. Log in, open **Lab Data Entry**.
2. Settings → Lab Catalog: add sample point `INLET` and parameters `pH (6.5–9.0)`, `COD (max 400)`; set `pH` to mirror a tag (optional).
3. Single Sample: enter pH=7.2, COD=999 → COD shows out-of-range red; Save.
4. Records: confirm the row; delete it as the owner.
5. Import: upload a small CSV (`time,pH` header) → map → commit → verify inserted count.
6. Grafana: open the **Lab Quality** dashboard → confirm the point/parameter variables populate and the time-series renders (requires TimescaleDB/Postgres, not SQLite dev — note this in the doc).
7. If a parameter was mirrored: open Advanced Reports → confirm the mirrored tag is selectable.

Capture a screenshot of the Single Sample tab with the out-of-range warning.

- [ ] **Step 4: Write the feature doc**

Create `docs/lab-data-entry.md` covering: purpose, the 4 entry modes, hybrid catalog + approval, mirror-to-tag for SCADA-panel comparison + report reuse, the `v_lab_timeseries` view + Grafana `lab-quality` dashboard, and the SQLite-dev caveat (view works but Grafana needs Postgres). Add a `## [Unreleased]` entry to `CHANGELOG.md`.

- [ ] **Step 5: Commit + push**

```bash
git add docs/lab-data-entry.md CHANGELOG.md
git commit -m "docs(lab): feature guide + changelog"
git push origin master
```

---

## Self-Review

**Spec coverage:**
- 4 tables + unified mixed-shape model → Task 1. ✓
- `v_lab_timeseries` view (primary Grafana bridge) → Task 1 (migration) + Task 6 (test + dashboard). ✓
- Optional mirror to `tag_readings` → Task 3 (`_build_sample`) + tests. ✓
- Hybrid catalog (admin-managed + operator add awaiting approval) → Task 2 + Task 8 (approval UI). ✓
- Entry modes: single (Task 3 API / Task 7 UI), batch (Task 3 / Task 8), import (Task 5 / Task 8), edit-delete (Task 4 / Task 8 Records). ✓
- Permissions: entry operator+admin (Task 3/4 `require_role`), edit/delete admin-or-owner (Task 4 `_assert_can_edit` + test), catalog approve admin (Task 2). ✓
- Audit on edit/delete → Task 4 (`record_audit` + tests). ✓
- Reports via advanced_reports reuse (mirror) → covered by mirror (Task 3) + verified in Task 9 step 3.7; no new generator code (matches spec). ✓
- License: no new gate; demo read-only via `require_writable` on all writes → Tasks 2-5. ✓
- Grafana provisioned dashboard + existing copy script → Task 6. ✓
- i18n 5 languages + nav → Task 7. ✓

**Placeholder scan:** No "TBD"/"implement later". Frontend Task 8's BatchTab/ImportTab/LabCatalogCard are described by behavior rather than full code — this is deliberate: they reuse the fully-shown patterns from Task 7/SingleSampleTab and the generated client, whose exact signatures must be read from `client.ts` post-`gen-client`. The pure, testable helpers (`isOutOfRange`, `canEditRecord`) have complete code + tests.

**Type consistency:** `_build_sample(db, data: SampleCreate, entered_by: int)` used identically in Tasks 3 and 5. `compute_flag` signature stable. `SampleOut`/`MeasurementOut`/`LabParameterOut`/`LabSamplePointOut` defined in Tasks 2-3 and consumed unchanged later. `canEditRecord(user, enteredBy)` and `isOutOfRange(value,min,max)` match their tests. Migration `down_revision="46644a7e7f25"` matches the verified head.

**Note on Task 6 step 2:** the view test may pass immediately (it re-creates the view from the same SQL) — that is expected; its value is asserting column/portability agreement with Task 1, not red-green on new code.
