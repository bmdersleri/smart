# Facility Variables Seeds + Workbook Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed a set of high-value shared facility variables backed by REAL plant flow tags, and migrate the daily-report (`gunluk_rapor.xlsx`) workbook's business formulas into a seeded Excel template whose columns bind to those variables — eliminating worksheet-side business logic (design Phases 3 + 7).

**Architecture:** Two idempotent seed scripts in the existing `app/seed_*.py` convention. `seed_facility_variables.py` resolves real `Tag` ids at runtime (by `node_id`) and creates variables THROUGH the `create_variable` service (validation + versioning + dependency/cycle checks — never raw INSERT), in dependency order so `ref`-composites resolve. `seed_excel_template.py` loads a committed workbook binary + a concrete column→variable binding map and persists an `ExcelTemplate` + `ExcelTemplateColumn` rows. Deployment-specific inputs (BAAT inflow tag, plant design capacity, the workbook file) are runtime config (env vars + a committed data file), not hardcoded guesses.

**Tech Stack:** Python 3.14, SQLAlchemy async, `app.core.database.AsyncSessionLocal`, `app.services.facility_variables.service.create_variable`, openpyxl (already a dep), pytest async (in-memory SQLite).

## Global Constraints

- Python baseline **3.14**; backend under `scada-reporter/backend/`; all `pytest`/`python -m` commands run from there (venv `.venv/`).
- Turkish docstrings/comments, `from __future__ import annotations`, type hints on public functions — match the existing `seed_*.py` files.
- **Seeds go through `create_variable`** (`app/services/facility_variables/service.py`), never a raw `FacilityVariable(...)` insert — this is the ONLY path that validates the expression, sets `version`, and records dependencies. Catch `IntegrityError`/`VariableError` per-variable.
- **Idempotent** like the existing seeds: SELECT existing keys (variable `code`, template `name`) into a set and skip rows already present — no upsert, no duplicate-error crash on re-run.
- **`window` in `agg`/`series` expression nodes is a STRING**, not a dict: `"day"`, `"7d"`, `"30d"`, `"month"`. (The preview-request `window` is a dict — that is a different thing and does NOT appear in stored expressions.) A dict here is a latent bug: it passes the validator's truthy check but the engine's `_window_bounds` only understands the string forms.
- **Totalizer semantics are explicit per tag.** Daily-reset totalizers (the `*.GUNLUK` tags) → `agg: "last"` over `window: "day"` gives the day's accumulated total. A cumulative/running totalizer (e.g. `GENEL_TOPLAM_DEBI`) → `agg: "delta"` over `window: "day"` gives the day's flow (last − first). Never `sum` a totalizer. Each seeded variable's choice is documented inline; the operator MUST verify numbers via the Plan-4 preview UI before trusting a migrated report.
- **No backend model/endpoint changes.** Every field used already exists (`FacilityVariable`, `ExcelTemplate`, `ExcelTemplateColumn`).
- Run the suite with the project runner; new tests are order-independent (shared in-memory SQLite, autouse table-clear).

## Backend Reference (verbatim — do not re-derive)

**`create_variable`** (`app/services/facility_variables/service.py`), keyword-only:
```python
await create_variable(
    db,                      # AsyncSession
    code=str, name=str, description=str,
    kind="scalar"|"series",  # must equal the expression root's inferred shape
    unit=str, value_type="number",
    expression=dict,         # validated by validate_expression(expression, kind)
    null_policy="skip"|"zero_fill"|"fail",
    quality_policy="good_only"|"allow_bad",
    default_time_grain="hour"|"day"|"week"|"month"|None,
    created_by=None,         # int|None
) -> FacilityVariable        # .id and .version available after; commits internally
```
- Raises `sqlalchemy.exc.IntegrityError` on duplicate `code` (unique). Raises `VariableError` (import from the same module) on validation failure. Does NOT pre-check existence — the seed must.
- Commits internally; do NOT wrap in `async with db.begin()`. Call once per variable inside the open session.

**Expression node shapes** (string windows!):
- `{"op":"const","value":<num>}` — scalar
- `{"op":"ref","variable_id":<int>}` — scalar (referenced variable must already exist)
- `{"op":"agg","source":{"type":"tag","tag_id":<int>},"agg":<AGG>,"window":<str>}` — scalar
- `{"op":"series","source":{"type":"tag","tag_id":<int>},"agg":<AGG>,"grain":<GRAIN>,"window":<str>}` — series
- `{"op":"reduce","reduce":<REDUCE>,"source":<series-node>}` — scalar
- `{"op":"add"|"sub"|"mul","args":[<node>,...]}`; `{"op":"div","on_zero":"null"|"zero"|"fail","args":[...]}`
- `AGG = sum|avg|min|max|last|delta`; `REDUCE = sum|avg|min|max|last`; `GRAIN = hour|day|week|month`.

**Real flow tags** (resolve `Tag.id` by `Tag.node_id` at runtime — ids are DB-assigned):
| node_id | meaning | totalizer kind → agg |
|---|---|---|
| `gtuTP02DB01.GUNLUK` | Terfi 1 daily total | daily-reset → `last`/`day` |
| `gtuTP01DB01.GUNLUK` | Terfi 2 daily total | daily-reset → `last`/`day` |
| `GENEL_TOPLAM_DEBI` | plant grand total | cumulative → `delta`/`day` |

**Deployment config (NOT in repo — provided at run time):**
- env `SEED_BAAT_GIRIS_NODE_ID` — the BAAT-section inflow tag's `node_id` (optional; BAAT-dependent variables are skipped when unset).
- env `SEED_AOT_DESIGN_CAPACITY_M3` — AÖT design capacity, m³/day, as a float (optional; the kapasite-fazlası variable is skipped when unset).
- file `app/seed_data/gunluk_rapor.xlsx` — the real daily-report workbook (committed by the operator; Task 4 seed errors clearly if absent).

**`ExcelTemplate` / `ExcelTemplateColumn` fields** (`app/models/excel_template.py`): template = `name`(unique), `description`, `file_blob`(LargeBinary NOT NULL), `sheet_name`, `header_row`, `date_col`, `data_start_row`, `date_mode`("write"|"match"), `created_by`. column = `col_letter`, `source_type`("tag"|"variable"), `variable_id`, `write_mode`("series"|"reduce"|None), `reduce_op`, `target_mode`("column"|"cell"), `target_cell`, `variable_code_snapshot`, `tag_id`, `agg`, `source_code`, `enabled`.

---

## File Structure

- Create: `app/seed_facility_variables.py` — variable seed (Task 1), grows BAAT/kapasite/composite (Task 2).
- Create: `app/seed_excel_template.py` — template+binding seed (Task 4).
- Create: `app/seed_data/` — holds the committed `gunluk_rapor.xlsx` (operator-supplied; Task 4 documents).
- Create: `tests/test_seed_facility_variables.py` (Task 3), `tests/test_seed_excel_template.py` (Task 5).
- Modify: `justfile` — `seed-facility-variables`, `seed-excel-template`, wire into `seed` (Task 6).
- Create: `docs/facility-variables-migration.md` — operator migration guide (Task 6).

---

### Task 1: Variable seed — concrete real-tag variables (no external config)

**Files:**
- Create: `app/seed_facility_variables.py`
- Test: covered by Task 3 (write the script here; its standalone behavior is asserted in Task 3 — but verify the run manually in Step 4).

**Interfaces:**
- Produces: `async def resolve_tag_id(db, node_id) -> int`; `async def seed_variables(db) -> dict[str, int]` returning a `{code: variable_id}` map of all created/existing variables (later tasks + the excel seed consume this map); `async def main() -> None`.

- [ ] **Step 1: Write the failing test** (minimal smoke; full coverage in Task 3)

Create `tests/test_seed_facility_variables.py` with one test that imports the module and runs the core variables against an in-memory DB seeded with the two terfi tags:
```python
import pytest
from sqlalchemy import select
from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag


@pytest.mark.asyncio
async def test_seed_creates_core_flow_variables(db_session):
    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
    ])
    await db_session.commit()

    from app.seed_facility_variables import seed_variables
    code_to_id = await seed_variables(db_session)

    assert "aot_giris_debi_gunluk" in code_to_id
    assert "terfi1_debi_gunluk" in code_to_id
    assert "terfi2_debi_gunluk" in code_to_id
    assert "tesis_toplam_debi_olculen_gunluk" in code_to_id
    assert "giris_7gun_ort_debi" in code_to_id

    rows = (await db_session.execute(select(FacilityVariable))).scalars().all()
    assert {r.code for r in rows} >= set(code_to_id)
    # the add-composite references the two terfi tag aggregations
    aot = next(r for r in rows if r.code == "aot_giris_debi_gunluk")
    assert aot.kind == "scalar"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py -p no:randomly -q`
Expected: FAIL — `app.seed_facility_variables` does not exist.

- [ ] **Step 3: Write `app/seed_facility_variables.py`**

```python
"""Tesis debisi facility-variable'larını idempotent şekilde ekler.

Gerçek katalog tag'lerini (node_id) çalışma zamanında çözer ve değişkenleri
create_variable servisi üzerinden oluşturur (validasyon + versiyon + bağımlılık
kaydı). Önce `just seed-catalog` çalıştırılmış olmalı.

Totalizer semantiği AÇIKTIR:
- `*.GUNLUK` = günlük resetlenen totalizer  → agg "last"  / window "day"
- `GENEL_TOPLAM_DEBI` = kümülatif totalizer → agg "delta" / window "day"
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import AsyncSessionLocal
from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag
from app.services.facility_variables.service import VariableError, create_variable


async def resolve_tag_id(db, node_id: str) -> int:
    """node_id'den Tag.id döndürür; yoksa anlaşılır hata verir."""
    row = await db.execute(select(Tag.id).where(Tag.node_id == node_id))
    tag_id = row.scalar_one_or_none()
    if tag_id is None:
        raise RuntimeError(f"Katalogda tag yok: {node_id!r} — önce `just seed-catalog` çalıştırın")
    return tag_id


def _agg(tag_id: int, agg: str, window: str = "day") -> dict:
    return {"op": "agg", "source": {"type": "tag", "tag_id": tag_id}, "agg": agg, "window": window}


async def seed_variables(db) -> dict[str, int]:
    """Çekirdek + (env varsa) BAAT/kapasite/kompozit değişkenleri ekler.

    Döner: {code: variable_id} — tüm oluşturulan VEYA zaten var olan değişkenler.
    Bağımlılık sırasına göre eklenir (ref-kompozitler sonra)."""
    terfi1 = await resolve_tag_id(db, "gtuTP02DB01.GUNLUK")  # Terfi 1 günlük totalizer
    terfi2 = await resolve_tag_id(db, "gtuTP01DB01.GUNLUK")  # Terfi 2 günlük totalizer
    genel = await resolve_tag_id(db, "GENEL_TOPLAM_DEBI")    # kümülatif grand total

    existing = await db.execute(select(FacilityVariable.code, FacilityVariable.id))
    code_to_id: dict[str, int] = {c: i for c, i in existing.all()}

    async def ensure(*, code: str, expression: dict, kind: str, name: str,
                     description: str, unit: str = "m3/gün", grain: str | None = "day") -> None:
        if code in code_to_id:
            print(f"  skip (var): {code}")
            return
        try:
            var = await create_variable(
                db, code=code, name=name, description=description, kind=kind, unit=unit,
                value_type="number", expression=expression, null_policy="skip",
                quality_policy="good_only", default_time_grain=grain, created_by=None,
            )
            code_to_id[code] = var.id
            print(f"  + {code} (id={var.id})")
        except (VariableError, IntegrityError) as exc:
            print(f"  HATA {code}: {exc}")

    # --- Çekirdek (her zaman, gerçek tag'ler) ---
    await ensure(
        code="terfi1_debi_gunluk", kind="scalar", name="Terfi 1 Çıkış Debi (Günlük)",
        description="Terfi 1 günlük totalizer son değeri", expression=_agg(terfi1, "last"),
    )
    await ensure(
        code="terfi2_debi_gunluk", kind="scalar", name="Terfi 2 Çıkış Debi (Günlük)",
        description="Terfi 2 günlük totalizer son değeri", expression=_agg(terfi2, "last"),
    )
    await ensure(
        code="aot_giris_debi_gunluk", kind="scalar", name="AÖT Tesise Alınan Debi (Günlük)",
        description="Terfi 1 + Terfi 2 günlük debisi toplamı",
        expression={"op": "add", "args": [_agg(terfi1, "last"), _agg(terfi2, "last")]},
    )
    await ensure(
        code="tesis_toplam_debi_olculen_gunluk", kind="scalar",
        name="Tesis Toplam Debi — Ölçülen (Günlük)",
        description="GENEL_TOPLAM_DEBI kümülatif totalizer günlük delta'sı",
        expression=_agg(genel, "delta"),
    )
    # 7-günlük ortalama giriş debisi: günlük delta serisini 7d penceresinde ortala
    await ensure(
        code="giris_7gun_ort_debi", kind="scalar", name="Giriş Debi — 7 Günlük Ortalama",
        description="GENEL_TOPLAM_DEBI günlük delta serisinin son 7 gün ortalaması",
        expression={
            "op": "reduce", "reduce": "avg",
            "source": {"op": "series", "source": {"type": "tag", "tag_id": genel},
                       "agg": "delta", "grain": "day", "window": "7d"},
        },
    )

    # --- Opsiyonel (deployment config) — Task 2 doldurur ---
    await _seed_optional(db, ensure, code_to_id)

    await db.commit()
    return code_to_id


async def _seed_optional(db, ensure, code_to_id: dict[str, int]) -> None:
    """BAAT / kapasite / kompozit — env yoksa atlanır. Task 2 implement eder."""
    return  # Task 2'de doldurulacak


async def main() -> None:
    async with AsyncSessionLocal() as db:
        created = await seed_variables(db)
        print(f"Bitti: {len(created)} değişken (oluşturulan+mevcut)")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py -p no:randomly -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/seed_facility_variables.py tests/test_seed_facility_variables.py
git commit -m "feat(facility-vars-seed): seed core flow variables (terfi/aot/tesis-toplam/7d-avg)"
```

---

### Task 2: Variable seed — optional BAAT / kapasite / composite (env-driven)

**Files:**
- Modify: `app/seed_facility_variables.py` (replace `_seed_optional` body)
- Test: add cases to `tests/test_seed_facility_variables.py`

**Interfaces:**
- Consumes: env `SEED_BAAT_GIRIS_NODE_ID`, `SEED_AOT_DESIGN_CAPACITY_M3`; the `code_to_id` map from Task 1 (for `ref` composites).
- Produces: when configured, variables `baat_giris_debi_gunluk`, `kapasite_fazlasi_gunluk`, `tesis_toplam_debi_hesaplanan_gunluk` (the migrated `aot+baat+kapasite` workbook formula, built from `ref` nodes).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_seed_facility_variables.py`:
```python
@pytest.mark.asyncio
async def test_seed_optional_baat_and_capacity(db_session, monkeypatch):
    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
        Tag(node_id="BAAT_GIRIS_X", name="BAAT_GIRIS_X", unit=""),
    ])
    await db_session.commit()
    monkeypatch.setenv("SEED_BAAT_GIRIS_NODE_ID", "BAAT_GIRIS_X")
    monkeypatch.setenv("SEED_AOT_DESIGN_CAPACITY_M3", "120000")

    from app.seed_facility_variables import seed_variables
    code_to_id = await seed_variables(db_session)

    assert "baat_giris_debi_gunluk" in code_to_id
    assert "kapasite_fazlasi_gunluk" in code_to_id
    assert "tesis_toplam_debi_hesaplanan_gunluk" in code_to_id


@pytest.mark.asyncio
async def test_seed_optional_skipped_without_env(db_session, monkeypatch):
    monkeypatch.delenv("SEED_BAAT_GIRIS_NODE_ID", raising=False)
    monkeypatch.delenv("SEED_AOT_DESIGN_CAPACITY_M3", raising=False)
    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
    ])
    await db_session.commit()
    from app.seed_facility_variables import seed_variables
    code_to_id = await seed_variables(db_session)
    assert "baat_giris_debi_gunluk" not in code_to_id
    assert "kapasite_fazlasi_gunluk" not in code_to_id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py -p no:randomly -q`
Expected: FAIL — optional variables not created (the env-set test fails).

- [ ] **Step 3: Implement `_seed_optional`**

Replace the `_seed_optional` stub:
```python
async def _seed_optional(db, ensure, code_to_id: dict[str, int]) -> None:
    """BAAT girişi + kapasite fazlası + hesaplanan tesis toplamı (ref kompoziti).

    Hepsi deployment config'e bağlıdır; ortam değişkeni yoksa sessizce atlanır."""
    baat_node = os.environ.get("SEED_BAAT_GIRIS_NODE_ID", "").strip()
    capacity_raw = os.environ.get("SEED_AOT_DESIGN_CAPACITY_M3", "").strip()

    if baat_node:
        baat_id = await resolve_tag_id(db, baat_node)
        await ensure(
            code="baat_giris_debi_gunluk", kind="scalar", name="BAAT Tesise Alınan Debi (Günlük)",
            description=f"BAAT giriş debisi ({baat_node}) günlük son değeri",
            expression=_agg(baat_id, "last"),
        )

    if capacity_raw and "aot_giris_debi_gunluk" in code_to_id:
        try:
            capacity = float(capacity_raw)
        except ValueError:
            print(f"  HATA: SEED_AOT_DESIGN_CAPACITY_M3 sayı değil: {capacity_raw!r}")
            return
        await ensure(
            code="kapasite_fazlasi_gunluk", kind="scalar", name="Kapasite Fazlası (Günlük)",
            description=f"Tasarım kapasitesi ({capacity:g} m3/gün) − AÖT giriş debisi",
            expression={"op": "sub", "args": [
                {"op": "const", "value": capacity},
                {"op": "ref", "variable_id": code_to_id["aot_giris_debi_gunluk"]},
            ]},
        )

    # Hesaplanan tesis toplamı = AÖT + BAAT + kapasite fazlası (workbook formülünün taşınmışı)
    needed = ("aot_giris_debi_gunluk", "baat_giris_debi_gunluk", "kapasite_fazlasi_gunluk")
    if all(c in code_to_id for c in needed):
        await ensure(
            code="tesis_toplam_debi_hesaplanan_gunluk", kind="scalar",
            name="Tesis Toplam Debi — Hesaplanan (Günlük)",
            description="AÖT + BAAT + kapasite fazlası (taşınan çalışma sayfası formülü)",
            expression={"op": "add", "args": [
                {"op": "ref", "variable_id": code_to_id["aot_giris_debi_gunluk"]},
                {"op": "ref", "variable_id": code_to_id["baat_giris_debi_gunluk"]},
                {"op": "ref", "variable_id": code_to_id["kapasite_fazlasi_gunluk"]},
            ]},
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py -p no:randomly -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/seed_facility_variables.py tests/test_seed_facility_variables.py
git commit -m "feat(facility-vars-seed): optional env-driven BAAT/kapasite/composite variables (ref nodes)"
```

---

### Task 3: Idempotency + expression-validity test

**Files:**
- Modify: `tests/test_seed_facility_variables.py`

**Interfaces:**
- Consumes: `seed_variables` (Tasks 1-2). Asserts re-running creates no duplicates and every seeded expression is accepted by the real validator (it already is, since `create_variable` validates — this test guards against future drift).

- [ ] **Step 1: Write the failing test** (it will pass once the assertions are right — this task hardens, run RED by temporarily breaking? No: write the test; it should PASS against the Task-2 code. Treat a FAIL here as a real regression.)

Append:
```python
@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session):
    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
    ])
    await db_session.commit()
    from app.seed_facility_variables import seed_variables
    first = await seed_variables(db_session)
    second = await seed_variables(db_session)
    assert first == second  # same code→id map, no new rows
    from sqlalchemy import func, select
    from app.models.facility_variable import FacilityVariable
    count = (await db_session.execute(select(func.count(FacilityVariable.id)))).scalar_one()
    assert count == len(first)  # no duplicates created on the second run


@pytest.mark.asyncio
async def test_seeded_expressions_pass_validator(db_session):
    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
    ])
    await db_session.commit()
    import json
    from app.services.facility_variables.expression import validate_expression
    from sqlalchemy import select
    from app.models.facility_variable import FacilityVariable
    from app.seed_facility_variables import seed_variables
    await seed_variables(db_session)
    for v in (await db_session.execute(select(FacilityVariable))).scalars().all():
        # round-trips through the real validator against its stored kind
        validate_expression(json.loads(v.expression_json), v.kind)
```
> If `FacilityVariable` stores the expression under a different attribute than `expression_json`, read the model and use the real attribute. `validate_expression` raises on failure (no return assertion needed).

- [ ] **Step 2: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py -p no:randomly -q`
Expected: PASS (all). A failure here is a real bug — fix the seed, not the test.

- [ ] **Step 3: Manual end-to-end smoke (optional, documented)**

With a real dev DB that has the catalog seeded:
```bash
.venv/Scripts/python -m app.seed_facility_variables
```
Expected: prints `+ <code>` lines, then `Bitti: N değişken`. Re-running prints `skip (var):` for all.

- [ ] **Step 4: Commit**

```bash
git add tests/test_seed_facility_variables.py
git commit -m "test(facility-vars-seed): idempotency + validator round-trip for seeded expressions"
```

---

### Task 4: Excel template seed — workbook + column→variable bindings

**Files:**
- Create: `app/seed_excel_template.py`
- Create: `app/seed_data/.gitkeep` (the operator commits `gunluk_rapor.xlsx` here)
- Test: covered by Task 5.

**Interfaces:**
- Consumes: the `{code: id}` map from `seed_variables`; a committed `app/seed_data/gunluk_rapor.xlsx`; a concrete `COLUMN_BINDINGS` map (design defaults below).
- Produces: `async def seed_excel_template(db, *, code_to_id) -> int | None` (returns the template id, or None if skipped); `async def main()`.

**`COLUMN_BINDINGS`** (design §510-515 defaults — operator edits to match the real sheet):
```
E  -> aot_giris_debi_gunluk          (AÖT tesise alınan debi)
F  -> kapasite_fazlasi_gunluk        (kapasite fazlası)
K  -> baat_giris_debi_gunluk         (BAAT tesise alınan debi)
M  -> tesis_toplam_debi_hesaplanan_gunluk  (tesis toplam debi)
```

- [ ] **Step 1: Write `app/seed_excel_template.py`**

```python
"""Günlük rapor Excel şablonunu + kolon→değişken bağlamalarını idempotent ekler.

Operatör gerçek çalışma kitabını `app/seed_data/gunluk_rapor.xlsx` olarak commit
etmeli. Şablon adı benzersizdir; varsa atlanır. Kolon haritası tasarım dokümanının
varsayılanıdır (E/F/K/M) — gerçek sayfaya göre düzenleyin.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.seed_facility_variables import seed_variables

TEMPLATE_NAME = "Günlük Rapor Şablonu"
WORKBOOK_PATH = Path(__file__).parent / "seed_data" / "gunluk_rapor.xlsx"

# Çalışma sayfası geometrisi — gerçek kitaba göre ayarlayın.
SHEET_META = dict(sheet_name="OCAK", header_row=2, date_col="D", data_start_row=5, date_mode="write")

# Kolon harfi -> değişken kodu (tasarım §510-515 varsayılanı)
COLUMN_BINDINGS: list[tuple[str, str]] = [
    ("E", "aot_giris_debi_gunluk"),
    ("F", "kapasite_fazlasi_gunluk"),
    ("K", "baat_giris_debi_gunluk"),
    ("M", "tesis_toplam_debi_hesaplanan_gunluk"),
]


async def seed_excel_template(db, *, code_to_id: dict[str, int]) -> int | None:
    """Şablon + bağlamaları ekler. Zaten varsa (ada göre) atlar, None döner."""
    if not WORKBOOK_PATH.exists():
        print(f"  ATLA: çalışma kitabı yok: {WORKBOOK_PATH} — gerçek gunluk_rapor.xlsx'i buraya commit edin")
        return None

    existing = await db.execute(select(ExcelTemplate.id).where(ExcelTemplate.name == TEMPLATE_NAME))
    found = existing.scalar_one_or_none()
    if found is not None:
        print(f"  skip (şablon var): {TEMPLATE_NAME} (id={found})")
        return found

    blob = WORKBOOK_PATH.read_bytes()
    tpl = ExcelTemplate(name=TEMPLATE_NAME, description="Tesis günlük debi raporu (seed)",
                        file_blob=blob, created_by=None, **SHEET_META)

    columns: list[ExcelTemplateColumn] = []
    for col_letter, var_code in COLUMN_BINDINGS:
        var_id = code_to_id.get(var_code)
        if var_id is None:
            print(f"  UYARI: {col_letter} → {var_code} değişkeni yok, kolon atlandı "
                  f"(env eksik olabilir)")
            continue
        columns.append(ExcelTemplateColumn(
            col_letter=col_letter, source_type="variable", variable_id=var_id,
            write_mode="reduce", reduce_op="last", target_mode="column",
            variable_code_snapshot=var_code, tag_id=None, agg="last",
            source_code=var_code, enabled=True,
        ))
    tpl.columns = columns
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    print(f"  + şablon {TEMPLATE_NAME} (id={tpl.id}), {len(columns)} kolon bağlandı")
    return tpl.id


async def main() -> None:
    async with AsyncSessionLocal() as db:
        code_to_id = await seed_variables(db)   # değişkenleri garanti et
        await seed_excel_template(db, code_to_id=code_to_id)


if __name__ == "__main__":
    asyncio.run(main())
```
> `write_mode="reduce"` + `reduce_op="last"` collapses each variable to one value per report row/period for a column target. If the real sheet wants a per-day series down a column, change to `write_mode="series"` for that column. Adjust `SHEET_META` + `COLUMN_BINDINGS` to the real workbook before relying on output.

- [ ] **Step 2: Create the seed-data placeholder**

Create `app/seed_data/.gitkeep` (empty). The operator commits `gunluk_rapor.xlsx` alongside it.

- [ ] **Step 3: Commit** (test added in Task 5)

```bash
git add app/seed_excel_template.py app/seed_data/.gitkeep
git commit -m "feat(facility-vars-seed): seed gunluk_rapor excel template + column→variable bindings"
```

---

### Task 5: Excel template seed test (synthetic workbook)

**Files:**
- Test: `tests/test_seed_excel_template.py`

**Interfaces:**
- Consumes: `seed_excel_template`, `seed_variables`. Uses a TINY openpyxl-generated workbook written to the real `WORKBOOK_PATH` via `monkeypatch`/`tmp_path` so the test never depends on the operator's real file.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from openpyxl import Workbook
from sqlalchemy import select
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.models.tag import Tag


def _tiny_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "OCAK"
    ws["D2"] = "Tarih"
    wb.save(path)


@pytest.mark.asyncio
async def test_seed_excel_template_binds_columns(db_session, tmp_path, monkeypatch):
    import app.seed_excel_template as mod
    wb_path = tmp_path / "gunluk_rapor.xlsx"
    _tiny_workbook(wb_path)
    monkeypatch.setattr(mod, "WORKBOOK_PATH", wb_path)

    db_session.add_all([
        Tag(node_id="gtuTP02DB01.GUNLUK", name="gtuTP02DB01.GUNLUK", unit=""),
        Tag(node_id="gtuTP01DB01.GUNLUK", name="gtuTP01DB01.GUNLUK", unit=""),
        Tag(node_id="GENEL_TOPLAM_DEBI", name="GENEL_TOPLAM_DEBI", unit=""),
    ])
    await db_session.commit()
    code_to_id = await mod.seed_variables(db_session)

    tid = await mod.seed_excel_template(db_session, code_to_id=code_to_id)
    assert tid is not None
    tpl = (await db_session.execute(select(ExcelTemplate).where(ExcelTemplate.id == tid))).scalar_one()
    cols = (await db_session.execute(
        select(ExcelTemplateColumn).where(ExcelTemplateColumn.col_letter == "E"))).scalars().all()
    # column E binds to the aot variable (always seeded)
    e_col = next(c for c in cols)
    assert e_col.source_type == "variable"
    assert e_col.variable_code_snapshot == "aot_giris_debi_gunluk"

    # idempotent: second call skips, returns same id
    again = await mod.seed_excel_template(db_session, code_to_id=code_to_id)
    assert again == tid


@pytest.mark.asyncio
async def test_seed_excel_template_skips_when_workbook_absent(db_session, tmp_path, monkeypatch):
    import app.seed_excel_template as mod
    monkeypatch.setattr(mod, "WORKBOOK_PATH", tmp_path / "nope.xlsx")
    out = await mod.seed_excel_template(db_session, code_to_id={})
    assert out is None
```

- [ ] **Step 2: Run it to verify it fails, then passes**

Run: `.venv/Scripts/python -m pytest tests/test_seed_excel_template.py -p no:randomly -q`
Expected: the binding test drives the real `seed_excel_template`; both pass. (If a column binds to a variable absent without env — F/K/M — it is skipped with a warning, which is fine; the test only asserts E.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_seed_excel_template.py
git commit -m "test(facility-vars-seed): excel template seed binds columns + idempotent + absent-workbook skip"
```

---

### Task 6: justfile wiring + operator migration guide

**Files:**
- Modify: `justfile`
- Create: `docs/facility-variables-migration.md`

**Interfaces:**
- Produces: `just seed-facility-variables`, `just seed-excel-template`, both wired after `seed-catalog`; a guide documenting the env vars, the workbook drop-in, the column map, run order, and the verify-via-preview step.

- [ ] **Step 1: Add justfile recipes**

After the existing `seed-deadband` recipe:
```just
seed-facility-variables:
    cd {{be}} && .venv/Scripts/python -m app.seed_facility_variables

seed-excel-template:
    cd {{be}} && .venv/Scripts/python -m app.seed_excel_template
```
Extend the composite `seed` recipe (currently `seed: seed-users seed-catalog`) to:
```just
seed: seed-users seed-catalog seed-facility-variables
```
> Do NOT add `seed-excel-template` to the composite — it requires the operator's committed workbook and is run explicitly.

- [ ] **Step 2: Write `docs/facility-variables-migration.md`**

A concise operator guide containing: (1) prerequisites (`just seed-catalog` first); (2) the core variables table (code, formula, totalizer assumption); (3) the env vars `SEED_BAAT_GIRIS_NODE_ID` + `SEED_AOT_DESIGN_CAPACITY_M3` with examples; (4) how to commit the real `gunluk_rapor.xlsx` to `app/seed_data/` and adjust `SHEET_META` + `COLUMN_BINDINGS`; (5) run order (`just seed-facility-variables` then `just seed-excel-template`); (6) **verification**: open each seeded variable in the Plan-4 preview UI and confirm a sane value for a known day BEFORE trusting a generated report — totalizer semantics (`last` vs `delta`) are the most likely thing to need adjustment. Write it in Turkish to match the project's docs.

- [ ] **Step 3: Verify the recipes parse**

Run: `just --list 2>&1 | grep -E "seed-facility-variables|seed-excel-template"`
Expected: both recipes listed.

- [ ] **Step 4: Commit**

```bash
git add justfile docs/facility-variables-migration.md
git commit -m "docs(facility-vars-seed): justfile recipes + operator migration guide"
```

---

## Final Verification (run after all tasks)

```bash
cd scada-reporter/backend
.venv/Scripts/python -m pytest tests/test_seed_facility_variables.py tests/test_seed_excel_template.py -p no:randomly -q
.venv/Scripts/python -m ruff check app/seed_facility_variables.py app/seed_excel_template.py
.venv/Scripts/python -m mypy app/seed_facility_variables.py app/seed_excel_template.py
just --list | grep seed
```
Expected: all seed tests green, ruff + mypy clean, recipes listed. (Optional, with a real catalog-seeded dev DB: `just seed-facility-variables` then verify a variable in the preview UI.)

---

## Self-Review (author checklist — completed)

**1. Spec coverage (design Phase 3 + Phase 7 + Integration §503-515):**
- Phase 3 "seed a small set of high-value shared variables (total transfer flow, total plant inflow, 7-day average inflow)" → Task 1 (`aot_giris_debi_gunluk` = total transfer, `tesis_toplam_debi_olculen_gunluk` = total plant, `giris_7gun_ort_debi` = 7-day average). ✓
- Phase 7 / §503-509 "move workbook business formulas to backend variables" (`var_baat_giris_toplam`, `var_tesis_toplam = aot+baat+kapasite`) → Task 2 (`ref`-composite `tesis_toplam_debi_hesaplanan_gunluk`). ✓
- §510-515 "bind worksheet columns E/F/K/M → variables" → Task 4 (`COLUMN_BINDINGS`). ✓
- "variables are user-managed via service, not raw seeds" → all seeds go through `create_variable`. ✓

**2. Placeholder scan:** No TBD/TODO. Every code step is complete. The genuinely deployment-specific inputs (BAAT tag, capacity, the workbook binary, sheet geometry) are runtime config (env vars + a committed file + an editable `SHEET_META`/`COLUMN_BINDINGS`), NOT plan placeholders — the code that consumes them is fully written and tested with synthetic data. This is the correct seam: source code is complete; plant data is configuration.

**3. Type/shape consistency:** All expression `window` values are STRINGS (`"day"`/`"7d"`). Totalizer agg is explicit per tag (`last` for `*.GUNLUK`, `delta` for `GENEL_TOPLAM_DEBI`). `create_variable` is called with the exact keyword signature from the backend reference. `code_to_id` map threads Task 1 → 2 → 4 consistently. `ref` composites are seeded only after their dependencies exist (dependency-ordered).

**4. Known assumption flagged:** `GENEL_TOPLAM_DEBI` is treated as a cumulative totalizer (`delta`/day). If it is actually daily-reset, switch to `last`. The migration guide (Task 6) makes verification-before-trust mandatory.

---

## Execution Handoff

Recommended: **subagent-driven-development** — one fresh subagent per task, two-stage review between tasks, matching Plans 1-4. Ledger under a Plan-5 section in `.superpowers/sdd/progress.md`. Base before Task 1: current `master` HEAD.

**Operator follow-up (outside this plan, required before the migrated report is trustworthy):** commit the real `gunluk_rapor.xlsx`, set the two env vars, adjust `SHEET_META`/`COLUMN_BINDINGS` to the real sheet, run the seeds, and verify each variable in the preview UI.
