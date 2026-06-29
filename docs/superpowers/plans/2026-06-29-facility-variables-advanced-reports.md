# Facility Variables — Advanced Reports + Archive Version Stamping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let advanced report templates select facility variables alongside raw tags, evaluate those variables at report-generation time into the Excel/PDF/JSON output, and stamp the resolved `(variable_id, code, version, window)` into the report archive so a generated report is auditable against the formula that produced it.

**Architecture:** Add a `variable_ids` JSON column to `report_templates` and a `variable_refs_json` column to `report_archive` (both additive, backward-compatible). A new focused service `app/services/report_variables.py` resolves selected variables over the report window by reusing the existing `evaluate_variable` entry point (so advanced reports, Excel fill, and preview all share one evaluation path) and a shared serializer extracted from `preview.py`. `generate_report_from_template` calls the resolver, renders the variables into each output format, embeds them in the compressed `result_json` summary, and stamps `variable_refs_json`. No new permissions or license gates are introduced — template create/edit are already permission-gated and the router already carries `require_feature("advanced_reports")`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x (async), Alembic, openpyxl (Excel), WeasyPrint (PDF), pytest-asyncio. Dev/test DB is in-memory SQLite (shared StaticPool engine, autouse table-clear fixture in `tests/conftest.py`).

## Global Constraints

- Python baseline is **3.14** — never lower CI/metadata to 3.12 (deferred-annotation `ua.Node` only imports on 3.14).
- Backend lives under `scada-reporter/backend/`; **all `just`/`pytest`/`alembic` commands run from that directory** (the venv is `.venv/`, managed by `uv`).
- New code matches the existing file convention: **Turkish docstrings/comments**, `from __future__ import annotations`, type hints on public functions.
- **Single alembic head** at all times. Current head before this plan: `f3a4b5c6d7e8`. Each migration's `down_revision` chains to the previous task's revision; verify `alembic heads` shows exactly one head after each migration task.
- **Backward compatibility is mandatory.** Existing templates (no `variable_ids`) and existing archives (no `variable_refs_json`) must keep working unchanged. New columns get a `server_default`/`nullable=True` so old rows read cleanly.
- **One evaluation path.** Variable evaluation goes through `app.services.facility_variables.resolver.evaluate_variable` — do NOT re-implement bucketing or ref-resolution. Divergence between report rendering and Excel fill / preview is a bug (design doc "Output shape contract", "engine/daily_rollup divergence" risk).
- **Time zone.** All bucketing is tz-sensitive via `settings.REPORT_TZ_OFFSET_HOURS`. Readings are stored UTC-naive; the report window must be normalized to **naive UTC** before being handed to the engine, and the same offset threads to every leaf (design doc "Time zone").
- Run the full suite with `just test` (parallel, randomized). Tests must be order-independent — never rely on data written by another test.

---

## File Map

- Modify: `scada-reporter/backend/app/models/report_template.py`
  Add `variable_ids` JSON-text column (selected facility-variable ids).
- Modify: `scada-reporter/backend/app/models/report_archive.py`
  Add `variable_refs_json` text column (resolved variable refs for audit).
- Create: `scada-reporter/backend/alembic/versions/<rev1>_report_template_variable_ids.py`
  Migration adding `report_templates.variable_ids`.
- Create: `scada-reporter/backend/alembic/versions/<rev2>_report_archive_variable_refs.py`
  Migration adding `report_archive.variable_refs_json`.
- Modify: `scada-reporter/backend/app/services/facility_variables/preview.py`
  Extract `serialize_eval_result(...)` so preview and report rendering share one serializer.
- Create: `scada-reporter/backend/app/services/report_variables.py`
  `resolve_report_variables(...)` — evaluate selected variables over the report window, return render data + audit refs.
- Modify: `scada-reporter/backend/app/services/report_generator.py`
  Call the resolver; render variables into JSON output + compressed summary; stamp `variable_refs_json`.
- Modify: `scada-reporter/backend/app/services/excel_builder.py`
  Add a "Tesis Değişkenleri" worksheet when variables are present.
- Modify: `scada-reporter/backend/app/services/pdf_builder.py`
  Add a facility-variables section when variables are present.
- Modify: `scada-reporter/backend/app/api/advanced_reports.py`
  Round-trip `variable_ids` in template create/update/response; expose `variable_refs` in archive response.
- Test: `scada-reporter/backend/tests/test_report_variables.py` (new) — resolver unit tests.
- Test: `scada-reporter/backend/tests/test_report_generator_variables.py` (new) — orchestrator integration + stamping.
- Test: `scada-reporter/backend/tests/test_advanced_reports_variables_api.py` (new) — API round-trip + end-to-end stamping.
- Modify: `scada-reporter/backend/tests/test_facility_variable_preview.py` — keep green after serializer extraction.

---

## Interfaces (shared contract across tasks)

These names are fixed; every task uses exactly these signatures.

```python
# app/services/facility_variables/preview.py  (Task 3)
def serialize_eval_result(result: EvalResult, unit: str, tz_offset_hours: int) -> dict:
    """EvalResult -> {"kind":"scalar","value":float|None,"unit":str}
                  or {"kind":"series","points":[{"ts":iso,"value":float|None}],"unit":str}."""

# app/services/report_variables.py  (Task 3)
async def resolve_report_variables(
    db: AsyncSession,
    variable_ids: list[int],
    *,
    start: datetime,   # naive UTC
    end: datetime,     # naive UTC
    tz_offset_hours: int,
) -> tuple[list[dict], list[dict]]:
    """Returns (per_variable_data, variable_refs).

    per_variable_data item (for rendering):
      {"variable_id": int, "code": str, "name": str, "unit": str,
       "kind": "scalar"|"series",
       "value": float|None,                 # scalar only, else None
       "points": [{"ts": iso, "value": ...}]|None,  # series only, else None
       "warning": str|None}

    variable_refs item (for audit/stamping):
      {"variable_id": int, "code": str, "version": int,
       "window": {"start": iso, "end": iso, "grain": str, "tz_offset_hours": int},
       "warning": str|None}
    """
```

`EvalResult` (existing, `app/services/facility_variables/engine.py`) has `.kind` (`"scalar"|"series"`), `.scalar: float|None`, `.series: dict[date|datetime, float|None]|None`.

`evaluate_variable(db, var, *, start, end, grain, tz_offset_hours) -> EvalResult` is the existing single entry point (`app/services/facility_variables/resolver.py`).

---

### Task 1: Template `variable_ids` field + migration + API round-trip

**Files:**
- Modify: `scada-reporter/backend/app/models/report_template.py` (after `tag_ids`, line 14)
- Create: `scada-reporter/backend/alembic/versions/<rev1>_report_template_variable_ids.py`
- Modify: `scada-reporter/backend/app/api/advanced_reports.py` (TemplateCreate ~64, TemplateResponse ~87/110-115, create_template ~206-237, update_template ~252-284)
- Test: `scada-reporter/backend/tests/test_advanced_reports_variables_api.py` (new)

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `ReportTemplate.variable_ids: Mapped[str]` (JSON text, default `"[]"`); `TemplateCreate.variable_ids: list[int]`; `TemplateResponse.variable_ids: list[int]`.

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_advanced_reports_variables_api.py`:

```python
"""Advanced report templates round-trip selected facility variable ids."""

import pytest


@pytest.mark.asyncio
async def test_template_roundtrips_variable_ids(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    body = {
        "name": "VarTemplate",
        "tag_ids": [],
        "variable_ids": [11, 22],
        "output_format": "json",
    }
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    tid = resp.json()["id"]
    assert resp.json()["variable_ids"] == [11, 22]

    got = await client.get(f"/api/advanced-reports/templates/{tid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["variable_ids"] == [11, 22]


@pytest.mark.asyncio
async def test_template_variable_ids_default_empty(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    body = {"name": "NoVars", "tag_ids": [1], "output_format": "json"}
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["variable_ids"] == []
```

> **Fixture note:** reuse the existing `client` + `admin_token` fixtures used by `tests/test_advanced_reports_*` / `tests/test_facility_variables_api.py`. If those fixtures live in `conftest.py` under different names, copy the exact names from one of those test modules — do not invent new fixtures.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_advanced_reports_variables_api.py -v -p no:randomly`
Expected: FAIL — `variable_ids` not accepted / not returned (KeyError or 422 / assertion on `[11, 22]`).

- [ ] **Step 3a: Add the model column**

In `app/models/report_template.py`, immediately after the `tag_ids` line (line 14):

```python
    tag_ids: Mapped[str] = mapped_column(Text)  # JSON "[1,2,3]"
    variable_ids: Mapped[str] = mapped_column(
        Text, default="[]", server_default="[]"
    )  # JSON "[11,22]" — seçili tesis değişkeni id'leri
```

- [ ] **Step 3b: Create the migration**

Generate a revision id and create `alembic/versions/<rev1>_report_template_variable_ids.py`. Use a fixed, readable revision id (e.g. `a1b2c3d4e5f6`). `down_revision` MUST be `"f3a4b5c6d7e8"` (current head).

```python
"""report_templates.variable_ids

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_templates",
        sa.Column("variable_ids", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("report_templates", "variable_ids")
```

- [ ] **Step 3c: Round-trip the field in the API**

In `app/api/advanced_reports.py`:

`TemplateCreate` (after `tag_ids: list[int]`, line 64):
```python
    tag_ids: list[int]
    variable_ids: list[int] = []
```

`TemplateResponse` (after `tag_ids: list[int]`, line 87):
```python
    tag_ids: list[int]
    variable_ids: list[int]
```

`TemplateResponse.from_orm` (after the `tag_ids` json.loads, line 112):
```python
        data["tag_ids"] = json.loads(obj.tag_ids)
        data["variable_ids"] = json.loads(obj.variable_ids)
```

`create_template` — in the `ReportTemplate(...)` constructor (near `tag_ids=json.dumps(body.tag_ids),`):
```python
        tag_ids=json.dumps(body.tag_ids),
        variable_ids=json.dumps(body.variable_ids),
```

`update_template` — next to `tmpl.tag_ids = json.dumps(body.tag_ids)`:
```python
    tmpl.tag_ids = json.dumps(body.tag_ids)
    tmpl.variable_ids = json.dumps(body.variable_ids)
```

- [ ] **Step 4: Apply the migration, run the test**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic heads   # expect exactly ONE head: a1b2c3d4e5f6
.venv/Scripts/python -m pytest tests/test_advanced_reports_variables_api.py -v -p no:randomly
```
Expected: both tests PASS; single alembic head.

- [ ] **Step 5: Commit**

```bash
git add app/models/report_template.py alembic/versions/a1b2c3d4e5f6_report_template_variable_ids.py app/api/advanced_reports.py tests/test_advanced_reports_variables_api.py
git commit -m "feat(advanced-reports): select facility variables on a template (variable_ids round-trip + migration)"
```

---

### Task 2: Archive `variable_refs_json` column + migration

**Files:**
- Modify: `scada-reporter/backend/app/models/report_archive.py` (after `result_json`, line 36-38)
- Create: `scada-reporter/backend/alembic/versions/<rev2>_report_archive_variable_refs.py`
- Test: `scada-reporter/backend/tests/test_report_generator_variables.py` (new — first test only)

**Interfaces:**
- Consumes: Task 1's migration as `down_revision`.
- Produces: `ReportArchive.variable_refs_json: Mapped[str | None]` (nullable text, default `None`).

- [ ] **Step 1: Write the failing test**

Create `scada-reporter/backend/tests/test_report_generator_variables.py`:

```python
"""report_archive stores resolved facility-variable refs; orchestrator renders variables."""

import gzip
import json
from datetime import UTC, datetime

import pytest

from app.models.report_archive import ReportArchive


@pytest.mark.asyncio
async def test_archive_has_variable_refs_column(db_session):
    arch = ReportArchive(
        status="pending",
        trigger="manual",
        tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC),
        end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily",
        output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    assert arch.variable_refs_json is None
    arch.variable_refs_json = json.dumps([{"variable_id": 1, "code": "x", "version": 1}])
    await db_session.commit()
    await db_session.refresh(arch)
    assert json.loads(arch.variable_refs_json)[0]["code"] == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_archive_has_variable_refs_column -v -p no:randomly`
Expected: FAIL — `AttributeError`/`TypeError` (`variable_refs_json` not a column).

- [ ] **Step 3a: Add the model column**

In `app/models/report_archive.py`, after the `result_json` column (lines 36-38):

```python
    result_json: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )  # gzip-compressed summary
    variable_refs_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: çözülen (variable_id, code, version, window) — denetim/sürüm damgası
```

(`Text` is already imported at the top of the file.)

- [ ] **Step 3b: Create the migration**

Create `alembic/versions/<rev2>_report_archive_variable_refs.py`, revision id e.g. `b2c3d4e5f6a7`, `down_revision = "a1b2c3d4e5f6"`:

```python
"""report_archive.variable_refs_json

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_archive",
        sa.Column("variable_refs_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report_archive", "variable_refs_json")
```

- [ ] **Step 4: Apply migration, run the test**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic heads   # expect ONE head: b2c3d4e5f6a7
.venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_archive_has_variable_refs_column -v -p no:randomly
```
Expected: PASS; single head.

- [ ] **Step 5: Commit**

```bash
git add app/models/report_archive.py alembic/versions/b2c3d4e5f6a7_report_archive_variable_refs.py tests/test_report_generator_variables.py
git commit -m "feat(advanced-reports): add report_archive.variable_refs_json for version stamping (migration)"
```

---

### Task 3: Shared serializer + `resolve_report_variables` service

**Files:**
- Modify: `scada-reporter/backend/app/services/facility_variables/preview.py`
- Create: `scada-reporter/backend/app/services/report_variables.py`
- Test: `scada-reporter/backend/tests/test_report_variables.py` (new)
- Test: `scada-reporter/backend/tests/test_facility_variable_preview.py` (must stay green)

**Interfaces:**
- Consumes: `evaluate_variable` (existing), `EvalResult` (existing).
- Produces: `serialize_eval_result(result, unit, tz_offset_hours) -> dict`; `resolve_report_variables(db, variable_ids, *, start, end, tz_offset_hours) -> tuple[list[dict], list[dict]]` (exact shapes in the top-level Interfaces section).

- [ ] **Step 1: Write the failing tests**

Create `scada-reporter/backend/tests/test_report_variables.py`:

```python
"""resolve_report_variables: evaluate selected variables over the report window."""

import json
from datetime import datetime

import pytest

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag, TagReading
from app.services.report_variables import resolve_report_variables


async def _seed_tag(db, name="P", unit="m3"):
    tag = Tag(node_id=f"ns=2;s={name}", name=name, unit=unit)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


async def _add_var(db, *, code, kind, expr, unit="m3", grain="day", active=True, version=1):
    var = FacilityVariable(
        code=code,
        name=code,
        kind=kind,
        unit=unit,
        expression_json=json.dumps(expr),
        default_time_grain=grain,
        is_active=active,
        version=version,
    )
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


@pytest.mark.asyncio
async def test_scalar_variable_resolves_value_and_ref(db_session):
    tag = await _seed_tag(db_session)
    # two readings same day -> delta = last - first = 40
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 20), value=50.0))
    await db_session.commit()
    var = await _add_var(
        db_session,
        code="var_daily",
        kind="scalar",
        version=4,
        expr={
            "op": "reduce",
            "reduce": "sum",
            "source": {
                "op": "series",
                "source": {"type": "tag", "tag_id": tag.id},
                "agg": "delta",
                "grain": "day",
            },
        },
    )
    per_var, refs = await resolve_report_variables(
        db_session, [var.id], start=datetime(2026, 6, 1), end=datetime(2026, 6, 2), tz_offset_hours=3
    )
    assert len(per_var) == 1
    item = per_var[0]
    assert item["kind"] == "scalar"
    assert item["code"] == "var_daily"
    assert item["value"] == pytest.approx(40.0)
    assert item["points"] is None
    assert item["warning"] is None
    assert refs[0] == {
        "variable_id": var.id,
        "code": "var_daily",
        "version": 4,
        "window": {
            "start": "2026-06-01T00:00:00",
            "end": "2026-06-02T00:00:00",
            "grain": "day",
            "tz_offset_hours": 3,
        },
        "warning": None,
    }


@pytest.mark.asyncio
async def test_series_variable_resolves_points(db_session):
    tag = await _seed_tag(db_session)
    for d, v in [(1, 5.0), (1, 15.0), (2, 20.0), (2, 50.0)]:
        db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, d, 12), value=v))
    await db_session.commit()
    var = await _add_var(
        db_session,
        code="var_series",
        kind="series",
        expr={
            "op": "series",
            "source": {"type": "tag", "tag_id": tag.id},
            "agg": "max",
            "grain": "day",
        },
    )
    per_var, _ = await resolve_report_variables(
        db_session, [var.id], start=datetime(2026, 6, 1), end=datetime(2026, 6, 3), tz_offset_hours=3
    )
    item = per_var[0]
    assert item["kind"] == "series"
    assert item["value"] is None
    # points sorted by bucket, ts carries +03:00 offset
    assert [p["value"] for p in item["points"]] == [15.0, 50.0]
    assert item["points"][0]["ts"].endswith("+03:00")


@pytest.mark.asyncio
async def test_inactive_variable_warns_not_silent(db_session):
    var = await _add_var(
        db_session,
        code="var_off",
        kind="scalar",
        active=False,
        expr={"op": "const", "value": 1.0},
    )
    per_var, refs = await resolve_report_variables(
        db_session, [var.id], start=datetime(2026, 6, 1), end=datetime(2026, 6, 2), tz_offset_hours=3
    )
    assert per_var[0]["warning"] is not None
    assert per_var[0]["value"] is None
    assert refs[0]["warning"] is not None


@pytest.mark.asyncio
async def test_missing_variable_id_warns(db_session):
    per_var, refs = await resolve_report_variables(
        db_session, [999999], start=datetime(2026, 6, 1), end=datetime(2026, 6, 2), tz_offset_hours=3
    )
    assert per_var[0]["warning"] is not None
    assert refs[0]["variable_id"] == 999999
    assert refs[0]["warning"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_variables.py -v -p no:randomly`
Expected: FAIL — `ModuleNotFoundError: app.services.report_variables`.

- [ ] **Step 3a: Extract the shared serializer in preview.py**

In `app/services/facility_variables/preview.py`, add a module-level function (keep `_iso_offset` as-is and reuse it) and refactor `preview_variable` to call it. Add this above `preview_variable`:

```python
def serialize_eval_result(result, unit: str, tz_offset_hours: int) -> dict:
    """EvalResult -> önizleme/rapor için ortak JSON şekli (tek serileştirme yolu)."""
    if result.kind == "scalar":
        return {"kind": "scalar", "value": result.scalar, "unit": unit}
    points = [
        {"ts": _iso_offset(k, tz_offset_hours), "value": v}
        for k, v in sorted((result.series or {}).items())
    ]
    return {"kind": "series", "points": points, "unit": unit}
```

Replace the tail of `preview_variable` (the `if result.kind == "scalar": ... return {...}` block) with:

```python
    return serialize_eval_result(result, var.unit, tz_offset_hours)
```

(`EvalResult` import is not needed for an untyped param; leave `from __future__ import annotations` in place. If you prefer a type hint, import `EvalResult` from `app.services.facility_variables.engine`.)

- [ ] **Step 3b: Create the resolver service**

Create `app/services/report_variables.py`:

```python
"""Seçili tesis değişkenlerini rapor penceresinde değerlendirir.

Tek değerlendirme yolu: evaluate_variable (Excel fill + preview ile aynı), tek
serileştirme: serialize_eval_result. Pasif/eksik değişken sessiz boş bırakmaz —
görünür uyarı döner ve denetim ref'i yine de kaydedilir (sürüm damgası).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.preview import serialize_eval_result
from app.services.facility_variables.resolver import evaluate_variable


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


async def resolve_report_variables(
    db: AsyncSession,
    variable_ids: list[int],
    *,
    start: datetime,
    end: datetime,
    tz_offset_hours: int,
) -> tuple[list[dict], list[dict]]:
    per_variable_data: list[dict] = []
    variable_refs: list[dict] = []

    for vid in variable_ids:
        var = await db.get(FacilityVariable, vid)

        if var is None:
            warning = f"Değişken bulunamadı (id={vid})"
            per_variable_data.append(
                {
                    "variable_id": vid,
                    "code": f"#{vid}",
                    "name": "",
                    "unit": "",
                    "kind": "scalar",
                    "value": None,
                    "points": None,
                    "warning": warning,
                }
            )
            variable_refs.append(
                {
                    "variable_id": vid,
                    "code": f"#{vid}",
                    "version": 0,
                    "window": {
                        "start": _iso(start),
                        "end": _iso(end),
                        "grain": "day",
                        "tz_offset_hours": tz_offset_hours,
                    },
                    "warning": warning,
                }
            )
            continue

        grain = var.default_time_grain or "day"
        window = {
            "start": _iso(start),
            "end": _iso(end),
            "grain": grain,
            "tz_offset_hours": tz_offset_hours,
        }

        if not var.is_active:
            warning = f"{var.code}: değişken pasif"
            per_variable_data.append(
                {
                    "variable_id": var.id,
                    "code": var.code,
                    "name": var.name,
                    "unit": var.unit,
                    "kind": var.kind,
                    "value": None,
                    "points": None,
                    "warning": warning,
                }
            )
            variable_refs.append(
                {
                    "variable_id": var.id,
                    "code": var.code,
                    "version": var.version,
                    "window": window,
                    "warning": warning,
                }
            )
            continue

        result = await evaluate_variable(
            db,
            var,
            start=start.replace(tzinfo=None),
            end=end.replace(tzinfo=None),
            grain=grain,
            tz_offset_hours=tz_offset_hours,
        )
        serialized = serialize_eval_result(result, var.unit, tz_offset_hours)
        per_variable_data.append(
            {
                "variable_id": var.id,
                "code": var.code,
                "name": var.name,
                "unit": var.unit,
                "kind": serialized["kind"],
                "value": serialized.get("value"),
                "points": serialized.get("points"),
                "warning": None,
            }
        )
        variable_refs.append(
            {
                "variable_id": var.id,
                "code": var.code,
                "version": var.version,
                "window": window,
                "warning": None,
            }
        )

    return per_variable_data, variable_refs
```

- [ ] **Step 4: Run both test modules**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_report_variables.py tests/test_facility_variable_preview.py -v -p no:randomly
```
Expected: all PASS (new resolver tests + preview tests still green after the serializer extraction).

- [ ] **Step 5: Commit**

```bash
git add app/services/facility_variables/preview.py app/services/report_variables.py tests/test_report_variables.py
git commit -m "feat(advanced-reports): resolve_report_variables service + shared eval-result serializer"
```

---

### Task 4: Wire variables into the orchestrator (compute + JSON output + summary + stamping)

**Files:**
- Modify: `scada-reporter/backend/app/services/report_generator.py` (imports; inside `generate_report_from_template`)
- Test: `scada-reporter/backend/tests/test_report_generator_variables.py` (add integration tests)

**Interfaces:**
- Consumes: `resolve_report_variables` (Task 3); `ReportArchive.variable_refs_json` (Task 2); `ReportTemplate.variable_ids` (Task 1, read via `getattr` for fake-template safety).
- Produces: `archive.variable_refs_json` populated; `result_json` summary gains a `"variables"` key; JSON output gains a `"variables"` key. `per_variable_data` passed to builders (Tasks 5/6) as a new kwarg `variables=`.

> **Note on fake templates:** `tests/test_report_generator.py` uses a `_Template` dataclass without `variable_ids`. Read it defensively: `json.loads(getattr(template, "variable_ids", None) or "[]")` — mirrors the existing `getattr(template, "grafana_panels", None)` pattern at line 151. Do NOT change the fake dataclass.

- [ ] **Step 1: Write the failing tests**

Append to `scada-reporter/backend/tests/test_report_generator_variables.py`:

```python
from dataclasses import dataclass


@dataclass
class _VarTemplate:
    tag_ids: str = "[]"
    variable_ids: str = "[]"
    time_range_type: str = "custom"
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    interval: str = "daily"
    output_format: str = "json"
    percentile_levels: str = "[50]"
    include_std_dev: bool = True
    include_percentiles: bool = True
    include_trend_line: bool = False
    anomaly_enabled: bool = False
    anomaly_zscore_threshold: float = 3.0
    show_summary_stats: bool = True
    show_trend_charts: bool = False
    show_anomaly_table: bool = False
    show_raw_data: bool = False
    grafana_panels: str = "[]"


async def _make_scalar_var(db, version=2):
    from app.models.facility_variable import FacilityVariable
    from app.models.tag import Tag, TagReading

    tag = Tag(node_id="ns=2;s=VG", name="VG", unit="m3")
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    db.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 20), value=70.0))
    await db.commit()
    var = FacilityVariable(
        code="var_orch",
        name="Orch Var",
        kind="scalar",
        unit="m3",
        version=version,
        default_time_grain="day",
        expression_json=json.dumps(
            {
                "op": "reduce",
                "reduce": "sum",
                "source": {
                    "op": "series",
                    "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta",
                    "grain": "day",
                },
            }
        ),
    )
    db.add(var)
    await db.commit()
    await db.refresh(var)
    return var


@pytest.mark.asyncio
async def test_orchestrator_stamps_variable_refs(db_session):
    from app.services.report_generator import generate_report_from_template

    var = await _make_scalar_var(db_session, version=7)
    arch = ReportArchive(
        status="pending", trigger="manual", tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC), end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily", output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)

    tmpl = _VarTemplate(
        variable_ids=json.dumps([var.id]),
        custom_start=datetime(2026, 6, 1, tzinfo=UTC),
        custom_end=datetime(2026, 6, 2, tzinfo=UTC),
    )
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id, lang="tr"
    )
    await db_session.refresh(arch)
    assert arch.status == "completed"
    refs = json.loads(arch.variable_refs_json)
    assert refs[0]["variable_id"] == var.id
    assert refs[0]["version"] == 7
    # compressed summary carries the variable values
    summary = json.loads(gzip.decompress(arch.result_json))
    assert summary["variables"][0]["code"] == "var_orch"
    assert summary["variables"][0]["value"] == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_json_output_file_includes_variables(db_session, tmp_path, monkeypatch):
    import os as _os

    from app.services.report_generator import generate_report_from_template

    monkeypatch.chdir(tmp_path)
    var = await _make_scalar_var(db_session)
    arch = ReportArchive(
        status="pending", trigger="manual", tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC), end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily", output_format="json",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    tmpl = _VarTemplate(variable_ids=json.dumps([var.id]))
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id
    )
    await db_session.refresh(arch)
    with open(arch.file_path) as f:
        payload = json.load(f)
    assert payload["variables"][0]["code"] == "var_orch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_generator_variables.py -v -p no:randomly`
Expected: the two new tests FAIL (`variable_refs_json` is None / no `"variables"` key); `test_archive_has_variable_refs_column` still passes.

- [ ] **Step 3a: Import the resolver + settings/tz**

At the top of `app/services/report_generator.py` add (after the existing imports):

```python
from app.services.report_variables import resolve_report_variables
```

(`settings` is already imported at line 12.)

- [ ] **Step 3b: Resolve variables inside `generate_report_from_template`**

After the `per_tag_data` loop completes and before "Summary bar chart" (around line 142, after the `for tag_id ...` loop), insert:

```python
        # --- Tesis değişkenleri (rapor penceresinde değerlendir) ---
        variable_ids: list[int] = json.loads(getattr(template, "variable_ids", None) or "[]")
        tz_offset = settings.REPORT_TZ_OFFSET_HOURS
        win_start = start.replace(tzinfo=None)
        win_end = end.replace(tzinfo=None)
        per_variable_data, variable_refs = await resolve_report_variables(
            db, variable_ids, start=win_start, end=win_end, tz_offset_hours=tz_offset
        )
```

- [ ] **Step 3c: Pass variables to builders + JSON output**

Update the Excel/PDF builder calls to pass `variables=per_variable_data` (the builders accept it as a keyword in Tasks 5/6; add the kwarg now so the wiring is in place):

```python
        if template.output_format == "excel":
            content = build_advanced_excel(
                archive,
                per_tag_data,
                template,
                summary_chart,
                lang=lang,
                grafana_charts=grafana_charts,
                variables=per_variable_data,
            )
            ext = "xlsx"
        elif template.output_format == "pdf":
            generated_at = datetime.now(UTC)
            content = build_pdf(
                archive,
                per_tag_data,
                template,
                settings.FACILITY_NAME,
                generated_at,
                lang=lang,
                grafana_charts=grafana_charts,
                variables=per_variable_data,
            )
            ext = "pdf"
        else:
            # JSON
            serialized = {
                "archive_id": archive_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "tags": [
                    {
                        "tag_id": td["tag"].id,
                        "tag_name": td["tag"].name,
                        "stats": asdict(td["stats"]),
                        "anomaly_count": len(td["anomalies"]),
                        "period_rows": td["period_rows"],
                    }
                    for td in per_tag_data
                ],
                "variables": per_variable_data,
            }
            content = json.dumps(serialized, default=str).encode()
            ext = "json"
```

> The builders in Tasks 5/6 add `variables=None` as a default keyword, so adding the kwarg here is safe even before those tasks land within a subagent run that executes tasks in order. If executing strictly task-by-task, Tasks 5/6 follow immediately; the Excel/PDF integration tests are not part of this task.

- [ ] **Step 3d: Embed in the compressed summary + stamp the archive**

Replace the `summary = {...}` block (lines 229-239) and add the stamp before `await db.commit()`:

```python
        # Compressed summary for DB
        summary = {
            "tags": [
                {
                    "name": td["tag"].name,
                    "stats": asdict(td["stats"]),
                    "anomaly_count": len(td["anomalies"]),
                }
                for td in per_tag_data
            ],
            "variables": per_variable_data,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        archive.result_json = gzip.compress(json.dumps(summary, default=str).encode())
        archive.variable_refs_json = json.dumps(variable_refs) if variable_refs else None
        archive.file_path = file_path
```

- [ ] **Step 4: Run the tests**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_report_generator_variables.py tests/test_report_generator.py -v -p no:randomly
```
Expected: all PASS (new variable tests + existing orchestrator tests — no regression; `getattr` keeps the fake `_Template` working).

- [ ] **Step 5: Commit**

```bash
git add app/services/report_generator.py tests/test_report_generator_variables.py
git commit -m "feat(advanced-reports): evaluate selected variables in report generation, stamp variable_refs_json"
```

---

### Task 5: Render variables into the Excel output

**Files:**
- Modify: `scada-reporter/backend/app/services/excel_builder.py` (`build_advanced_excel` signature + new sheet)
- Test: `scada-reporter/backend/tests/test_report_generator_variables.py` (add Excel render test)

**Interfaces:**
- Consumes: `per_variable_data` items (Task 3 shape).
- Produces: `build_advanced_excel(..., variables: list[dict] | None = None)` writes a "Tesis Değişkenleri" worksheet when `variables` is non-empty.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report_generator_variables.py`:

```python
@pytest.mark.asyncio
async def test_excel_output_has_variables_sheet(db_session, tmp_path, monkeypatch):
    from io import BytesIO

    from openpyxl import load_workbook

    from app.services.report_generator import generate_report_from_template

    monkeypatch.chdir(tmp_path)
    var = await _make_scalar_var(db_session)
    arch = ReportArchive(
        status="pending", trigger="manual", tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC), end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily", output_format="excel",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    tmpl = _VarTemplate(output_format="excel", variable_ids=json.dumps([var.id]))
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id
    )
    await db_session.refresh(arch)
    wb = load_workbook(BytesIO(open(arch.file_path, "rb").read()))
    assert "Tesis Değişkenleri" in wb.sheetnames
    ws = wb["Tesis Değişkenleri"]
    codes = [row[0] for row in ws.iter_rows(min_row=2, values_only=True)]
    assert "var_orch" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_excel_output_has_variables_sheet -v -p no:randomly`
Expected: FAIL — `build_advanced_excel() got an unexpected keyword argument 'variables'` OR sheet missing.

- [ ] **Step 3: Add the sheet to `build_advanced_excel`**

In `app/services/excel_builder.py`, change the signature of `build_advanced_excel` to accept `variables`:

```python
def build_advanced_excel(
    archive,
    per_tag_data,
    template,
    summary_chart,
    *,
    lang: str = "en",
    grafana_charts=None,
    variables=None,
):
```

> Match the existing parameter style — if the current signature uses positional `lang`/`grafana_charts` rather than keyword-only, mirror that exactly; only ADD `variables=None` as the last parameter. Read the current signature first.

Just before the workbook is saved/returned at the end of `build_advanced_excel`, add:

```python
    if variables:
        vws = wb.create_sheet("Tesis Değişkenleri")
        _header_row(vws, ["Kod", "Ad", "Birim", "Tür", "Değer / Seri", "Uyarı"], row=1)
        r = 2
        for v in variables:
            if v["kind"] == "scalar":
                val_str = "" if v["value"] is None else f"{v['value']}"
            else:
                pts = v.get("points") or []
                val_str = f"{len(pts)} nokta"
            vws.cell(row=r, column=1, value=v["code"])
            vws.cell(row=r, column=2, value=v["name"])
            vws.cell(row=r, column=3, value=v["unit"])
            vws.cell(row=r, column=4, value=v["kind"])
            vws.cell(row=r, column=5, value=val_str)
            vws.cell(row=r, column=6, value=v.get("warning") or "")
            r += 1
```

> `wb` is the existing `Workbook` object in the function and `_header_row` is the existing helper (line 14). Confirm the local variable name for the workbook (`wb`) by reading the function; adjust if it differs.

- [ ] **Step 4: Run the test**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_excel_output_has_variables_sheet tests/test_report_generator.py -v -p no:randomly
```
Expected: PASS; existing Excel report tests still green.

- [ ] **Step 5: Commit**

```bash
git add app/services/excel_builder.py tests/test_report_generator_variables.py
git commit -m "feat(advanced-reports): render facility variables into Excel output (Tesis Değişkenleri sheet)"
```

---

### Task 6: Render variables into the PDF output

**Files:**
- Modify: `scada-reporter/backend/app/services/pdf_builder.py` (`build_pdf` signature + section)
- Test: `scada-reporter/backend/tests/test_report_generator_variables.py` (add PDF smoke test)

**Interfaces:**
- Consumes: `per_variable_data` items (Task 3 shape).
- Produces: `build_pdf(..., variables: list[dict] | None = None)` includes a facility-variables section when `variables` is non-empty.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report_generator_variables.py`:

```python
@pytest.mark.asyncio
async def test_pdf_output_renders_with_variables(db_session, tmp_path, monkeypatch):
    from app.services.report_generator import generate_report_from_template

    monkeypatch.chdir(tmp_path)
    var = await _make_scalar_var(db_session)
    arch = ReportArchive(
        status="pending", trigger="manual", tag_ids="[]",
        start=datetime(2026, 6, 1, tzinfo=UTC), end=datetime(2026, 6, 2, tzinfo=UTC),
        interval="daily", output_format="pdf",
    )
    db_session.add(arch)
    await db_session.commit()
    await db_session.refresh(arch)
    tmpl = _VarTemplate(output_format="pdf", variable_ids=json.dumps([var.id]))
    await generate_report_from_template(
        tmpl, datetime(2026, 6, 1), datetime(2026, 6, 2), db_session, arch.id
    )
    await db_session.refresh(arch)
    assert arch.status == "completed"
    assert arch.file_size_bytes and arch.file_size_bytes > 0
    assert arch.file_path.endswith(".pdf")
```

> This is a **smoke test** (PDF bytes are opaque; WeasyPrint requires GTK3, present on this box). It asserts generation succeeds with variables present and that the new `variables=` kwarg threads through without error. If WeasyPrint is unavailable in the runner, mark with `@pytest.mark.skipif` mirroring however existing PDF tests guard it — check `tests/test_report_generator.py` for the established pattern first.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_pdf_output_renders_with_variables -v -p no:randomly`
Expected: FAIL — `build_pdf() got an unexpected keyword argument 'variables'`.

- [ ] **Step 3: Add the section to `build_pdf`**

In `app/services/pdf_builder.py`, add `variables=None` as the last keyword parameter of `build_pdf` (mirror the existing signature's keyword style; read it first). Then locate where the HTML string is assembled and append a variables section before the closing `</body>` (or before the document is rendered):

```python
    variables_html = ""
    if variables:
        rows = ""
        for v in variables:
            if v["kind"] == "scalar":
                val = "" if v["value"] is None else f"{v['value']}"
            else:
                val = f"{len(v.get('points') or [])} nokta"
            warn = v.get("warning") or ""
            rows += (
                f"<tr><td>{v['code']}</td><td>{v['name']}</td>"
                f"<td>{v['unit']}</td><td>{v['kind']}</td>"
                f"<td>{val}</td><td>{warn}</td></tr>"
            )
        variables_html = (
            "<h2>Tesis Değişkenleri</h2>"
            "<table><thead><tr><th>Kod</th><th>Ad</th><th>Birim</th>"
            "<th>Tür</th><th>Değer / Seri</th><th>Uyarı</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
```

Then splice `variables_html` into the existing HTML template at the appropriate point (where tag tables are emitted). If `build_pdf` uses an f-string or template engine, insert `{variables_html}` in the body. **Read the function to find the exact assembly point** — the goal is: section appears after tag content, omitted entirely when `variables` is empty/None.

- [ ] **Step 4: Run the test**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_report_generator_variables.py::test_pdf_output_renders_with_variables tests/test_report_generator.py -v -p no:randomly
```
Expected: PASS; existing PDF report tests still green.

- [ ] **Step 5: Commit**

```bash
git add app/services/pdf_builder.py tests/test_report_generator_variables.py
git commit -m "feat(advanced-reports): render facility variables section into PDF output"
```

---

### Task 7: Expose `variable_refs` in the archive API + end-to-end stamping test

**Files:**
- Modify: `scada-reporter/backend/app/api/advanced_reports.py` (`ArchiveEntryResponse` + `from_orm`)
- Test: `scada-reporter/backend/tests/test_advanced_reports_variables_api.py` (add end-to-end test)

**Interfaces:**
- Consumes: `ReportArchive.variable_refs_json` (Task 2); `run_template` endpoint (existing); resolver+stamping (Task 4).
- Produces: `ArchiveEntryResponse.variable_refs: list[dict] | None` populated from `variable_refs_json`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_advanced_reports_variables_api.py`:

```python
import json

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag, TagReading
from datetime import datetime


@pytest.mark.asyncio
async def test_run_template_stamps_variable_refs_via_api(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}

    tag = Tag(node_id="ns=2;s=ApiVG", name="ApiVG", unit="m3")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 1), value=10.0))
    db_session.add(TagReading(tag_id=tag.id, timestamp=datetime(2026, 6, 1, 22), value=90.0))
    await db_session.commit()
    var = FacilityVariable(
        code="var_api",
        name="Api Var",
        kind="scalar",
        unit="m3",
        version=3,
        default_time_grain="day",
        expression_json=json.dumps(
            {
                "op": "reduce",
                "reduce": "sum",
                "source": {
                    "op": "series",
                    "source": {"type": "tag", "tag_id": tag.id},
                    "agg": "delta",
                    "grain": "day",
                },
            }
        ),
    )
    db_session.add(var)
    await db_session.commit()
    await db_session.refresh(var)

    create = await client.post(
        "/api/advanced-reports/templates",
        json={
            "name": "ApiVarTmpl",
            "tag_ids": [],
            "variable_ids": [var.id],
            "output_format": "json",
            "time_range_type": "custom",
            "custom_start": "2026-06-01T00:00:00",
            "custom_end": "2026-06-02T00:00:00",
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    tid = create.json()["id"]

    run = await client.post(
        f"/api/advanced-reports/templates/{tid}/run",
        json={"start": "2026-06-01T00:00:00", "end": "2026-06-02T00:00:00"},
        headers=headers,
    )
    assert run.status_code == 202, run.text
    archive_id = run.json()["id"]

    # BackgroundTasks run synchronously within the TestClient request lifecycle;
    # the archive should be completed with stamped refs by the time we fetch it.
    got = await client.get(f"/api/advanced-reports/archive/{archive_id}", headers=headers)
    assert got.status_code == 200, got.text
    refs = got.json()["variable_refs"]
    assert refs and refs[0]["variable_id"] == var.id
    assert refs[0]["version"] == 3
```

> **Background-task timing caveat:** FastAPI `BackgroundTasks` run after the response is sent but within the same test transport. If the archive is still `pending` when fetched (the `_run` task opens its own `AsyncSessionLocal`), this test may need to assert on a re-fetch or the test must drive `generate_report_from_template` directly instead of via `run_template`. **If the async background task does not complete deterministically under the test client, replace the `/run` call with a direct `await generate_report_from_template(...)` against a fetched template + pre-created archive (as in Task 4), then assert the API `GET /archive/{id}` exposes `variable_refs`.** The non-negotiable assertion is: the archive GET response includes a populated `variable_refs`. Pick whichever drive path is deterministic in this suite.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scada-reporter/backend && .venv/Scripts/python -m pytest tests/test_advanced_reports_variables_api.py -v -p no:randomly`
Expected: the new test FAILS — `variable_refs` not in the archive response (KeyError).

- [ ] **Step 3: Expose `variable_refs` in `ArchiveEntryResponse`**

In `app/api/advanced_reports.py`, `ArchiveEntryResponse` (after `file_size_bytes: int | None`, line 166):

```python
    file_size_bytes: int | None
    variable_refs: list[dict] | None
```

In `ArchiveEntryResponse.from_orm` (after `data.pop("result_json", None)`, line 174):

```python
        data["tag_ids"] = json.loads(obj.tag_ids)
        data.pop("result_json", None)
        raw_refs = data.pop("variable_refs_json", None)
        data["variable_refs"] = json.loads(raw_refs) if raw_refs else None
```

- [ ] **Step 4: Run the full new-test set + the existing archive API tests**

Run:
```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_advanced_reports_variables_api.py -v -p no:randomly
.venv/Scripts/python -m pytest tests/ -k "advanced_reports or report_generator or report_variables or facility_variable" -p no:randomly
```
Expected: all PASS; no regression in advanced-reports / report-generator / facility-variable suites.

- [ ] **Step 5: Commit**

```bash
git add app/api/advanced_reports.py tests/test_advanced_reports_variables_api.py
git commit -m "feat(advanced-reports): expose variable_refs on archive entries (version-stamp audit surface)"
```

---

## Final Verification (run after all tasks)

```bash
cd scada-reporter/backend
.venv/Scripts/python -m alembic heads          # exactly ONE head: b2c3d4e5f6a7
just lint
just typecheck
just test                                       # full suite, parallel + randomized — all green
```

Expected: single alembic head, ruff + mypy clean, full suite passes (the prior baseline was 807; this plan adds ~16 tests across 3 new test modules — expect ~823+).

---

## Self-Review (author checklist — completed)

**1. Spec coverage:**
- design §517-521 "Advanced reports ... select facility variables in addition to raw tags" → Tasks 1, 4, 5, 6 (template field + evaluate + render).
- design §342-348 "Archive and workbook metadata" / version stamping `(variable_id, code, version, window)` → Tasks 2, 4, 7.
- design §583 "archive version stamping — generated archive records resolved (variable_id, version)" → Task 4 test `test_orchestrator_stamps_variable_refs` + Task 7 API test.
- design §581 "advanced report variable rendering tests" → Tasks 5 (Excel), 6 (PDF), 4 (JSON).
- design "Output shape contract" / "one shared primitive" → Task 3 reuses `evaluate_variable` + `serialize_eval_result` (no re-implementation).
- design "Time zone" → Task 3/4 normalize window to naive UTC + thread `REPORT_TZ_OFFSET_HOURS`.
- design "dangling-binding"/silent-blank risk → Task 3 inactive/missing variables emit a visible `warning` (not silent), surfaced in render data + refs.
- **Out of scope (correctly deferred):** UI (Plan 4); variable seeds + `gunluk_rapor.xlsx` column migration (Plan 5); workbook `_scada_metadata` hidden-sheet stamping for *direct Excel template* generation (this plan stamps the *advanced-report archive* path — direct-template stamping is an Excel-binding concern tracked separately).

**2. Placeholder scan:** No TBD/TODO. Every code step carries complete code. The two adaptive spots (Task 6 WeasyPrint skip pattern, Task 7 background-task drive path) give an explicit decision rule + a deterministic fallback, not a vague "handle it".

**3. Type consistency:** `resolve_report_variables` and `serialize_eval_result` signatures are identical everywhere they appear (top Interfaces block + Task 3 def + Task 4 call). Render-item dict keys (`code/name/unit/kind/value/points/warning`) are identical across Tasks 3/5/6. Ref-item keys (`variable_id/code/version/window/warning`) identical across Tasks 3/4/7. Migration revision chain: `f3a4b5c6d7e8 → a1b2c3d4e5f6 → b2c3d4e5f6a7` (single head preserved).

---

## Execution Handoff

Recommended: **subagent-driven-development** — one fresh subagent per task, two-stage review (spec compliance + quality) between tasks, matching how Plans 1 and 2 were executed. Ledger this run under a Plan-3 section in `.superpowers/sdd/progress.md` (or `progress-spec3.md` if `progress.md` is owned by concurrent automation), with briefs/reports namespaced and review packages SHA-named.
