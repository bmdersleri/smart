# UI/UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add alarm thresholds to tags, alarm band on dashboard, tag edit modal, dual Y-axis trend chart, grouped report tag selection, and report download history.

**Architecture:** Backend-first — Tag model gets `min_alarm`/`max_alarm` columns, a new `ReportHistory` table stores the last 10 reports, and `current-values` response gains `alarm_state`. Frontend consumes these additions one page at a time: Dashboard → Tags → Trend → Reports.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + SQLite (dev) · React + Vite + TanStack Query v5 + Recharts 3 + Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-06-15-ui-ux-improvements-design.md`

---

## File Map

### Backend — modified
- `scada-reporter/backend/app/models/tag.py` — add `min_alarm`, `max_alarm` columns to `Tag`
- `scada-reporter/backend/app/models/report_history.py` — NEW: `ReportHistory` model
- `scada-reporter/backend/app/api/tags.py` — add `TagUpdate` schema + `PATCH /{tag_id}` endpoint; extend `TagResponse` with alarm fields
- `scada-reporter/backend/app/api/dashboard.py` — compute `alarm_state` in `current_values`; extend response schema
- `scada-reporter/backend/app/api/reports.py` — save history on generate; add `GET /history` + `GET /history/{id}/download`
- `scada-reporter/backend/app/main.py` — ensure `reports/` directory exists on startup

### Backend — new
- `scada-reporter/backend/alembic/versions/<hash>_alarm_thresholds_and_report_history.py` — migration

### Frontend — modified
- `scada-reporter/frontend/src/api/client.ts` — add `updateTag`, `getReportHistory`, `downloadHistoryReport` calls; extend `Tag` and `CurrentValue` interfaces
- `scada-reporter/frontend/src/pages/Dashboard.tsx` — alarm banner + row highlight + PLC connection stat card
- `scada-reporter/frontend/src/pages/Tags.tsx` — search box + edit modal with alarm fields; rename "Sil" to icon; rename "Format ?" to "Format" (keep modal, just rename)
- `scada-reporter/frontend/src/pages/Trend.tsx` — clear default selection; tag search filter; dual Y-axis with unit grouping; toast on 3rd unit
- `scada-reporter/frontend/src/pages/Reports.tsx` — grouped tag chips with "Select All"; report history section

### Tests — modified/new
- `scada-reporter/backend/tests/test_api.py` — extend with PATCH tag, alarm_state, report history tests

---

## Task 1: Backend — Tag model alarm fields + migration

**Files:**
- Modify: `scada-reporter/backend/app/models/tag.py`
- Create: `scada-reporter/backend/alembic/versions/<hash>_alarm_thresholds_and_report_history.py`

- [ ] **Step 1: Add `min_alarm` and `max_alarm` to `Tag` model**

Edit `scada-reporter/backend/app/models/tag.py`. Replace the existing `Tag` class body with:

```python
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(50), default="")
    channel: Mapped[str] = mapped_column(String(255), default="")
    device: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    readings: Mapped[list["TagReading"]] = relationship(back_populates="tag")
```

- [ ] **Step 2: Create `ReportHistory` model in a new file**

Create `scada-reporter/backend/app/models/report_history.py`:

```python
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class ReportHistory(Base):
    __tablename__ = "report_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tag_ids: Mapped[str] = mapped_column(Text, nullable=False)   # JSON: "[1,2,3]"
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)   # "hourly"|"daily"
    format: Mapped[str] = mapped_column(String(10), nullable=False)     # "excel"|"json"
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd scada-reporter/backend
.venv\Scripts\activate  # Windows
alembic revision --autogenerate -m "alarm_thresholds_and_report_history"
```

Open the generated file in `alembic/versions/`. Verify it contains:
- `ADD COLUMN min_alarm FLOAT` on `tags`
- `ADD COLUMN max_alarm FLOAT` on `tags`
- `CREATE TABLE report_history` with all columns

- [ ] **Step 4: Apply migration**

```bash
alembic upgrade head
```

Expected output: `Running upgrade <prev> -> <new>, alarm_thresholds_and_report_history`

- [ ] **Step 5: Commit**

```bash
git add app/models/tag.py app/models/report_history.py alembic/versions/
git commit -m "feat: add alarm thresholds to Tag model and ReportHistory table"
```

---

## Task 2: Backend — PATCH /api/tags/{tag_id} endpoint

**Files:**
- Modify: `scada-reporter/backend/app/api/tags.py`
- Modify: `scada-reporter/backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

In `scada-reporter/backend/tests/test_api.py`, add after the existing tag tests:

```python
@pytest.mark.anyio
async def test_patch_tag_alarm_thresholds(client: AsyncClient):
    # Create a tag first
    reg = await client.post("/api/auth/register", json={
        "username": "patchuser", "email": "p@test.com",
        "password": "test123", "role": "admin"
    })
    token_r = await client.post("/api/auth/token",
        data={"username": "patchuser", "password": "test123"})
    token = token_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    tag_r = await client.post("/api/tags/",
        json={"node_id": "DB99,REAL0", "name": "PatchTest", "unit": "m3/h"},
        headers=headers)
    assert tag_r.status_code == 201
    tag_id = tag_r.json()["id"]

    # PATCH alarm thresholds
    patch_r = await client.patch(f"/api/tags/{tag_id}",
        json={"min_alarm": 0.0, "max_alarm": 5000.0},
        headers=headers)
    assert patch_r.status_code == 200
    data = patch_r.json()
    assert data["min_alarm"] == 0.0
    assert data["max_alarm"] == 5000.0

    # PATCH unit only
    patch_r2 = await client.patch(f"/api/tags/{tag_id}",
        json={"unit": "bar"},
        headers=headers)
    assert patch_r2.status_code == 200
    assert patch_r2.json()["unit"] == "bar"
    assert patch_r2.json()["max_alarm"] == 5000.0  # unchanged
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scada-reporter/backend
pytest tests/test_api.py::test_patch_tag_alarm_thresholds -v
```

Expected: `FAILED` — 405 Method Not Allowed (no PATCH endpoint yet).

- [ ] **Step 3: Extend `TagResponse` and add `TagUpdate` + PATCH endpoint**

In `scada-reporter/backend/app/api/tags.py`:

Add `TagUpdate` schema after `TagCreate`:

```python
class TagUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    device: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    min_alarm: Optional[float] = None
    max_alarm: Optional[float] = None
```

Extend `TagResponse` — add the two new fields:

```python
class TagResponse(BaseModel):
    id: int
    node_id: str
    name: str
    description: str
    unit: str
    channel: str
    device: str
    is_active: bool
    min_alarm: float | None
    max_alarm: float | None

    model_config = {"from_attributes": True}
```

Add the PATCH endpoint after `delete_tag`:

```python
@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadi")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    await db.commit()
    await db.refresh(tag)
    return tag
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api.py::test_patch_tag_alarm_thresholds -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/api/tags.py tests/test_api.py
git commit -m "feat: PATCH /api/tags/{id} endpoint with alarm threshold fields"
```

---

## Task 3: Backend — alarm_state in current-values response

**Files:**
- Modify: `scada-reporter/backend/app/api/dashboard.py`
- Modify: `scada-reporter/backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
@pytest.mark.anyio
async def test_current_values_alarm_state(client: AsyncClient):
    # Register + login
    await client.post("/api/auth/register", json={
        "username": "alarmuser", "email": "a@test.com",
        "password": "test123", "role": "admin"
    })
    token_r = await client.post("/api/auth/token",
        data={"username": "alarmuser", "password": "test123"})
    headers = {"Authorization": f"Bearer {token_r.json()['access_token']}"}

    r = await client.get("/api/dashboard/current-values", headers=headers)
    assert r.status_code == 200
    # Each item must have alarm_state key
    for item in r.json():
        assert "alarm_state" in item
        assert item["alarm_state"] in (None, "overflow", "min", "max")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api.py::test_current_values_alarm_state -v
```

Expected: `FAILED` — `alarm_state` key missing from response.

- [ ] **Step 3: Update `current_values` to join Tag alarm fields and compute `alarm_state`**

Replace the `current_values` function in `scada-reporter/backend/app/api/dashboard.py`:

```python
@router.get("/current-values")
async def current_values(
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    """Each active tag's latest reading with alarm_state."""
    subq = (
        select(TagReading.tag_id, func.max(TagReading.timestamp).label("max_ts"))
        .group_by(TagReading.tag_id)
        .subquery()
    )
    result = await db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.unit,
            Tag.device,
            Tag.min_alarm,
            Tag.max_alarm,
            TagReading.value,
            TagReading.timestamp,
            TagReading.quality,
        )
        .join(subq, Tag.id == subq.c.tag_id)
        .join(
            TagReading,
            (TagReading.tag_id == subq.c.tag_id)
            & (TagReading.timestamp == subq.c.max_ts),
        )
        .where(Tag.is_active)
        .order_by(Tag.device, Tag.name)
    )
    rows = result.all()

    def _alarm_state(value, quality, min_alarm, max_alarm):
        if value is None or quality != 192 or value > 1_000_000:
            return "overflow"
        if max_alarm is not None and value > max_alarm:
            return "max"
        if min_alarm is not None and value < min_alarm:
            return "min"
        return None

    return [
        {
            "tag_id": r[0],
            "name": r[1],
            "unit": r[2],
            "device": r[3],
            "value": r[6],
            "timestamp": r[7],
            "quality_ok": r[8] == 192,
            "alarm_state": _alarm_state(r[6], r[8], r[4], r[5]),
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api.py::test_current_values_alarm_state -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/dashboard.py tests/test_api.py
git commit -m "feat: add alarm_state to current-values endpoint"
```

---

## Task 4: Backend — Report history (save + list + download)

**Files:**
- Modify: `scada-reporter/backend/app/api/reports.py`
- Modify: `scada-reporter/backend/app/main.py`
- Modify: `scada-reporter/backend/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
@pytest.mark.anyio
async def test_report_history(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "username": "histuser", "email": "h@test.com",
        "password": "test123", "role": "admin"
    })
    token_r = await client.post("/api/auth/token",
        data={"username": "histuser", "password": "test123"})
    headers = {"Authorization": f"Bearer {token_r.json()['access_token']}"}

    # History starts empty
    hist_r = await client.get("/api/reports/history", headers=headers)
    assert hist_r.status_code == 200
    assert hist_r.json() == []

    # Generate a JSON report (no file write needed for json)
    gen_r = await client.post("/api/reports/generate", json={
        "tag_ids": [], "start": "2026-01-01T00:00:00",
        "end": "2026-01-02T00:00:00", "interval": "hourly", "format": "json"
    }, headers=headers)
    assert gen_r.status_code == 200

    # History now has 1 entry
    hist_r2 = await client.get("/api/reports/history", headers=headers)
    assert len(hist_r2.json()) == 1
    entry = hist_r2.json()[0]
    assert entry["format"] == "json"
    assert entry["interval"] == "hourly"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api.py::test_report_history -v
```

Expected: `FAILED` — `/api/reports/history` returns 404.

- [ ] **Step 3: Ensure `reports/` directory exists on startup**

In `scada-reporter/backend/app/main.py`, add after the existing imports:

```python
import os
```

Inside the `lifespan` function, before `yield`, add:

```python
    # Ensure report storage directory exists
    os.makedirs("reports", exist_ok=True)
```

- [ ] **Step 4: Rewrite `reports.py` with history support**

Replace the entire content of `scada-reporter/backend/app/api/reports.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from io import BytesIO
import json
import uuid
import os
import openpyxl
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.tag import Tag, TagReading
from app.models.report_history import ReportHistory

router = APIRouter(prefix="/reports", tags=["reports"])

REPORTS_DIR = "reports"


class ReportRequest(BaseModel):
    tag_ids: list[int]
    start: datetime
    end: datetime
    interval: str = "hourly"   # "hourly" | "daily"
    format: str = "excel"      # "excel" | "json"


async def _fetch_aggregated(
    tag_ids: list[int], start: datetime, end: datetime, interval: str, db: AsyncSession
) -> dict:
    from sqlalchemy import func
    if interval == "daily":
        period_expr = func.strftime("%Y-%m-%d", TagReading.timestamp)
    else:
        period_expr = func.strftime("%Y-%m-%d %H:00", TagReading.timestamp)

    result = await db.execute(
        select(
            Tag.id, Tag.name, Tag.unit,
            period_expr.label("period"),
            func.avg(TagReading.value).label("avg_val"),
            func.min(TagReading.value).label("min_val"),
            func.max(TagReading.value).label("max_val"),
            func.count(TagReading.timestamp).label("count"),
        )
        .join(TagReading, Tag.id == TagReading.tag_id)
        .where(Tag.id.in_(tag_ids), TagReading.timestamp >= start, TagReading.timestamp <= end)
        .group_by(Tag.id, Tag.name, Tag.unit, "period")
        .order_by(Tag.name, "period")
    )
    data: dict[str, list] = {}
    for _, name, unit, period, avg, mn, mx, cnt in result.all():
        key = f"{name} ({unit})" if unit else name
        data.setdefault(key, []).append({
            "period": period,
            "avg": round(avg, 3) if avg is not None else None,
            "min": round(mn, 3) if mn is not None else None,
            "max": round(mx, 3) if mx is not None else None,
            "count": cnt,
        })
    return data


async def _save_history(req: ReportRequest, file_path: str, db: AsyncSession) -> None:
    """Persist a ReportHistory record; evict oldest if > 10 exist."""
    record = ReportHistory(
        tag_ids=json.dumps(req.tag_ids),
        start=req.start,
        end=req.end,
        interval=req.interval,
        format=req.format,
        file_path=file_path,
    )
    db.add(record)
    await db.flush()   # get the ID

    # Keep only the 10 most recent
    result = await db.execute(
        select(ReportHistory).order_by(ReportHistory.created_at.asc())
    )
    all_records = result.scalars().all()
    if len(all_records) > 10:
        for old in all_records[:-10]:
            if os.path.exists(old.file_path):
                os.remove(old.file_path)
            await db.delete(old)

    await db.commit()


@router.post("/generate")
async def generate_report(
    req: ReportRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    data = await _fetch_aggregated(req.tag_ids, req.start, req.end, req.interval, db)
    file_id = str(uuid.uuid4())

    if req.format == "json":
        payload = {"period": req.interval, "start": req.start, "end": req.end, "data": data}
        file_path = os.path.join(REPORTS_DIR, f"{file_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str)
        await _save_history(req, file_path, db)
        return payload

    # Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ozet"
    ws["A1"] = "SCADA Raporu"
    ws["A2"] = f"Baslangic: {req.start.strftime('%d.%m.%Y %H:%M')}"
    ws["A3"] = f"Bitis: {req.end.strftime('%d.%m.%Y %H:%M')}"
    ws["A4"] = f"Interval: {req.interval}"
    for tag_name, rows in data.items():
        sheet = wb.create_sheet(title=tag_name[:31])
        sheet.append(["Donem", "Ortalama", "Minimum", "Maksimum", "Okuma Sayisi"])
        for row in rows:
            sheet.append([row["period"] or "", row["avg"], row["min"], row["max"], row["count"]])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    file_path = os.path.join(REPORTS_DIR, f"{file_id}.xlsx")
    with open(file_path, "wb") as f:
        f.write(buf.getvalue())
    await _save_history(req, file_path, db)

    filename = f"scada_rapor_{req.start.strftime('%Y%m%d')}_{req.end.strftime('%Y%m%d')}.xlsx"
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/history")
async def list_history(
    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)
):
    result = await db.execute(
        select(ReportHistory).order_by(ReportHistory.created_at.desc()).limit(10)
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "tag_ids": json.loads(r.tag_ids),
            "start": r.start,
            "end": r.end,
            "interval": r.interval,
            "format": r.format,
        }
        for r in records
    ]


@router.get("/history/{history_id}/download")
async def download_history(
    history_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(ReportHistory).where(ReportHistory.id == history_id))
    record = result.scalar_one_or_none()
    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")
    return FileResponse(record.file_path)
```

- [ ] **Step 5: Register `ReportHistory` with SQLAlchemy Base**

In `scada-reporter/backend/app/main.py`, add this import after the existing `from app.models.tag import ...` line, so `Base.metadata.create_all` discovers the new table:

```python
from app.models.report_history import ReportHistory as _ReportHistory  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/test_api.py::test_report_history -v
```

Expected: `PASSED`

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/api/reports.py app/models/report_history.py app/main.py tests/test_api.py
git commit -m "feat: report history — save last 10 reports, list and re-download"
```

---

## Task 5: Frontend API client — new calls

**Files:**
- Modify: `scada-reporter/frontend/src/api/client.ts`

- [ ] **Step 1: Extend `Tag` interface and add `updateTag`**

In `scada-reporter/frontend/src/api/client.ts`, update the `Tag` interface and add `updateTag`:

```typescript
export interface Tag {
  id: number
  node_id: string
  name: string
  unit: string
  device: string
  channel: string
  is_active: boolean
  min_alarm: number | null
  max_alarm: number | null
}

export interface TagUpdate {
  name?: string
  unit?: string
  device?: string
  channel?: string
  description?: string
  min_alarm?: number | null
  max_alarm?: number | null
}

export const updateTag = (id: number, data: TagUpdate) =>
  api.patch<Tag>(`/tags/${id}`, data)
```

- [ ] **Step 2: Extend `CurrentValue` interface with `alarm_state`**

Replace the existing `CurrentValue` interface:

```typescript
export interface CurrentValue {
  tag_id: number
  name: string
  unit: string
  device: string
  value: number | null
  timestamp: string
  quality_ok: boolean
  alarm_state: 'overflow' | 'min' | 'max' | null
}
```

- [ ] **Step 3: Add report history types and calls**

Add after `generateReport`:

```typescript
export interface ReportHistoryEntry {
  id: number
  created_at: string
  tag_ids: number[]
  start: string
  end: string
  interval: string
  format: string
}

export const getReportHistory = () =>
  api.get<ReportHistoryEntry[]>('/reports/history')

export const downloadHistoryReport = (id: number) =>
  api.get(`/reports/history/${id}/download`, { responseType: 'blob' })
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd scada-reporter/frontend
pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/api/client.ts
git commit -m "feat: extend API client with updateTag, alarm_state, report history"
```

---

## Task 6: Dashboard — alarm banner + row highlight + PLC stat card

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Replace `Dashboard.tsx` with the updated version**

Full replacement of `scada-reporter/frontend/src/pages/Dashboard.tsx`:

```tsx
import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCurrentValues, getOverview } from '../api/client'
import type { CurrentValue } from '../api/client'
import { format, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'

function QualityDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function rowStyle(alarmState: CurrentValue['alarm_state']): string {
  if (alarmState === 'overflow' || alarmState === 'max' || alarmState === 'min') {
    return alarmState === 'overflow'
      ? 'border-t border-gray-800 bg-red-950/60'
      : 'border-t border-gray-800 bg-yellow-950/60'
  }
  return 'border-t border-gray-800 hover:bg-gray-800/40 transition-colors'
}

function valueDisplay(tv: CurrentValue): string {
  if (tv.alarm_state === 'overflow') return 'OVERFLOW'
  if (tv.value === null) return '—'
  return `${tv.value.toFixed(2)} ${tv.unit}`
}

function valueColor(alarmState: CurrentValue['alarm_state']): string {
  if (alarmState === 'overflow') return 'text-red-400'
  if (alarmState === 'max' || alarmState === 'min') return 'text-red-400'
  return 'text-cyan-300'
}

function TagRow({ tv, rowRef }: { tv: CurrentValue; rowRef?: React.Ref<HTMLTableRowElement> }) {
  const ts = tv.timestamp ? format(parseISO(tv.timestamp), 'HH:mm:ss', { locale: tr }) : '—'
  return (
    <tr ref={rowRef} className={rowStyle(tv.alarm_state)} data-tag-id={tv.tag_id}>
      <td className="px-4 py-3 text-sm text-gray-300">{tv.device}</td>
      <td className="px-4 py-3 text-sm text-white font-medium">{tv.name}</td>
      <td className={`px-4 py-3 text-sm text-right font-mono ${valueColor(tv.alarm_state)}`}>
        {valueDisplay(tv)}
      </td>
      <td className="px-4 py-3 text-sm text-gray-400 text-right">{ts}</td>
      <td className="px-4 py-3 text-right">
        <QualityDot ok={tv.quality_ok} />
      </td>
    </tr>
  )
}

function AlarmBanner({
  alarms,
  onDismiss,
  onScrollTo,
}: {
  alarms: CurrentValue[]
  onDismiss: () => void
  onScrollTo: (tagId: number) => void
}) {
  if (alarms.length === 0) return null
  return (
    <div className="flex items-center gap-3 bg-red-950 border border-red-800 rounded-xl px-4 py-2.5">
      <span className="text-red-400 font-bold text-sm shrink-0">
        🔴 {alarms.length} ALARM
      </span>
      <div className="flex flex-wrap gap-x-3 gap-y-1 flex-1">
        {alarms.map((a) => (
          <button
            key={a.tag_id}
            onClick={() => onScrollTo(a.tag_id)}
            className="text-red-300 text-xs hover:text-white underline underline-offset-2"
          >
            {a.name}
            {a.alarm_state === 'overflow' ? ': overflow'
              : a.alarm_state === 'max' ? `: max aşımı (${a.value?.toFixed(0)})`
              : `: min altı (${a.value?.toFixed(0)})`}
          </button>
        ))}
      </div>
      <button onClick={onDismiss} className="text-red-600 hover:text-red-300 text-xs shrink-0">✕</button>
    </div>
  )
}

export default function Dashboard() {
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({})
  const [bannerDismissed, setBannerDismissed] = useState(false)

  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: () => getOverview().then((r) => r.data),
    refetchInterval: 10000,
  })
  const { data: values = [], isLoading } = useQuery({
    queryKey: ['current-values'],
    queryFn: () => getCurrentValues().then((r) => r.data),
    refetchInterval: 5000,
  })
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/health').then((r) => r.json()) as Promise<{ opc_connected: boolean }>,
    refetchInterval: 10000,
  })

  const alarms = values.filter((v) => v.alarm_state !== null)

  const byDevice = values.reduce<Record<string, CurrentValue[]>>((acc, v) => {
    const d = v.device || 'Diğer';
    (acc[d] ??= []).push(v)
    return acc
  }, {})

  const scrollTo = (tagId: number) => {
    rowRefs.current[tagId]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
        <span className="text-xs text-gray-500">5 sn'de bir güncellenir</span>
      </div>

      {!bannerDismissed && (
        <AlarmBanner
          alarms={alarms}
          onDismiss={() => setBannerDismissed(true)}
          onScrollTo={scrollTo}
        />
      )}

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Aktif Tag" value={overview?.active_tags ?? '—'} />
        <StatCard label="Son 24 Saat Okuma" value={overview?.readings_24h?.toLocaleString('tr') ?? '—'} />
        <StatCard
          label="Son Veri"
          value={overview?.last_reading ? format(parseISO(overview.last_reading), 'HH:mm:ss') : '—'}
          sub={overview?.last_reading ? format(parseISO(overview.last_reading), 'dd MMM yyyy', { locale: tr }) : undefined}
        />
        <StatCard
          label="PLC Bağlantı"
          value={health == null ? '...' : health.opc_connected ? '● Bağlı' : '✗ Kopuk'}
          sub={health?.opc_connected ? undefined : 'S7 bağlantısı yok'}
        />
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Yükleniyor...</div>
      ) : values.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <p className="text-gray-400">Henüz tag eklenmemiş.</p>
          <p className="text-gray-500 text-sm mt-1">Tag Yönetimi sayfasından PLC tag'lerini ekleyin.</p>
        </div>
      ) : (
        Object.entries(byDevice).map(([device, tvs]) => (
          <div key={device} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-sm font-semibold text-white">{device}</span>
              <span className="text-xs text-gray-500">({tvs.length} tag)</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wide">
                  <th className="px-4 py-2 text-left">Cihaz</th>
                  <th className="px-4 py-2 text-left">Tag</th>
                  <th className="px-4 py-2 text-right">Değer</th>
                  <th className="px-4 py-2 text-right">Saat</th>
                  <th className="px-4 py-2 text-right">Kalite</th>
                </tr>
              </thead>
              <tbody>
                {tvs.map((tv) => (
                  <TagRow
                    key={tv.tag_id}
                    tv={tv}
                    rowRef={(el) => { rowRefs.current[tv.tag_id] = el }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </div>
  )
}
```

- [ ] **Step 2: Start dev servers and verify in browser**

```bash
# Terminal 1
cd scada-reporter/backend && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2
cd scada-reporter/frontend && pnpm dev
```

Open `http://localhost:5173`. Log in as `admin / admin123`. Verify:
- 4 stat cards visible (Aktif Tag, Son 24H, Son Veri, **PLC Bağlantı**)
- `Havuz_Seviye` row has red background + shows `OVERFLOW`
- If alarm banner appears, clicking a tag name scrolls to that row
- `✕` dismisses the banner

- [ ] **Step 3: Commit**

```bash
git add src/pages/Dashboard.tsx
git commit -m "feat: dashboard alarm banner, overflow row highlight, PLC stat card"
```

---

## Task 7: Tags page — search box + edit modal

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Tags.tsx`

- [ ] **Step 1: Replace `Tags.tsx` with updated version**

Full replacement of `scada-reporter/frontend/src/pages/Tags.tsx`:

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTags, createTag, deleteTag, updateTag } from '../api/client'
import type { Tag } from '../api/client'
import { useAuth } from '../context/AuthContext'

function AddTagModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ node_id: '', name: '', unit: '', device: '', channel: '', description: '' })
  const mut = useMutation({
    mutationFn: createTag,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); onClose() },
  })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Yeni Tag Ekle</h2>
        {[
          { k: 'node_id', label: 'S7 Adresi', ph: 'DB1,REAL0' },
          { k: 'name', label: 'Tag Adı', ph: 'Hat Debisi' },
          { k: 'unit', label: 'Birim', ph: 'm³/h' },
          { k: 'device', label: 'Cihaz (PLC)', ph: 'PLC_1500' },
          { k: 'channel', label: 'Kanal', ph: 'Channel1' },
        ].map(({ k, label, ph }) => (
          <div key={k}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
              value={(form as Record<string, string>)[k]} onChange={set(k)} placeholder={ph}
            />
          </div>
        ))}
        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">İptal</button>
          <button
            onClick={() => mut.mutate(form)} disabled={!form.node_id || !form.name || mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Ekleniyor...' : 'Ekle'}
          </button>
        </div>
        {mut.isError && <p className="text-red-400 text-sm">Hata oluştu.</p>}
      </div>
    </div>
  )
}

function EditTagModal({ tag, onClose }: { tag: Tag; onClose: () => void }) {
  const qc = useQueryClient()
  const [minAlarm, setMinAlarm] = useState(tag.min_alarm != null ? String(tag.min_alarm) : '')
  const [maxAlarm, setMaxAlarm] = useState(tag.max_alarm != null ? String(tag.max_alarm) : '')
  const [unit, setUnit] = useState(tag.unit)
  const [device, setDevice] = useState(tag.device)
  const [channel, setChannel] = useState(tag.channel)
  const [validationErr, setValidationErr] = useState('')

  const mut = useMutation({
    mutationFn: (payload: Parameters<typeof updateTag>[1]) => updateTag(tag.id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); onClose() },
  })

  const save = () => {
    const min = minAlarm !== '' ? parseFloat(minAlarm) : null
    const max = maxAlarm !== '' ? parseFloat(maxAlarm) : null
    if (min !== null && max !== null && min >= max) {
      setValidationErr('Min değer Max\'tan küçük olmalı')
      return
    }
    setValidationErr('')
    mut.mutate({ unit, device, channel, min_alarm: min, max_alarm: max })
  }

  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{tag.name} — Düzenle</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">S7 Adresi (değiştirilemez)</label>
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-500 font-mono">{tag.node_id}</div>
        </div>

        {[
          { label: 'Birim', value: unit, set: setUnit, ph: 'm³/h' },
          { label: 'Cihaz', value: device, set: setDevice, ph: 'PLC_1500' },
          { label: 'Kanal', value: channel, set: setChannel, ph: 'Channel1' },
        ].map(({ label, value, set, ph }) => (
          <div key={label}>
            <label className="text-xs text-gray-400 mb-1 block">{label}</label>
            <input className={inputCls} value={value} onChange={(e) => set(e.target.value)} placeholder={ph} />
          </div>
        ))}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Min Alarm (boş = yok)</label>
            <input className={inputCls} type="number" value={minAlarm} onChange={(e) => setMinAlarm(e.target.value)} placeholder="0" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Max Alarm (boş = yok)</label>
            <input className={inputCls} type="number" value={maxAlarm} onChange={(e) => setMaxAlarm(e.target.value)} placeholder="5000" />
          </div>
        </div>

        {validationErr && <p className="text-red-400 text-sm">{validationErr}</p>}
        {mut.isError && <p className="text-red-400 text-sm">Kayıt hatası.</p>}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 text-sm transition-colors">İptal</button>
          <button
            onClick={save} disabled={mut.isPending}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {mut.isPending ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FormatGuideModal({ onClose }: { onClose: () => void }) {
  const examples = [
    { addr: 'DB1,REAL0', desc: 'DB1, REAL (32-bit float), offset 0' },
    { addr: 'DB2,INT4', desc: 'DB2, INT (16-bit signed), offset 4' },
    { addr: 'DB3,DINT8', desc: 'DB3, DINT (32-bit signed), offset 8' },
    { addr: 'DB4,WORD6', desc: 'DB4, WORD (16-bit unsigned), offset 6' },
    { addr: 'DB5,BOOL10.3', desc: 'DB5, BOOL, byte 10, bit 3' },
  ]
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">S7 Adres Formatı</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        <p className="text-gray-400 text-sm">Node ID alanına aşağıdaki formatta girin:</p>
        <div className="bg-gray-800 rounded-lg p-4 space-y-2">
          {examples.map(({ addr, desc }) => (
            <div key={addr} className="flex items-baseline gap-3">
              <span className="text-blue-400 font-mono text-sm w-32 flex-shrink-0">{addr}</span>
              <span className="text-gray-500 text-xs">{desc}</span>
            </div>
          ))}
        </div>
        <p className="text-gray-600 text-xs">Desteklenen tipler: REAL · INT · DINT · WORD · BOOL</p>
        <button onClick={onClose} className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors">Tamam</button>
      </div>
    </div>
  )
}

export default function Tags() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showFormat, setShowFormat] = useState(false)
  const [editTag, setEditTag] = useState<Tag | null>(null)
  const [search, setSearch] = useState('')

  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const delMut = useMutation({
    mutationFn: deleteTag,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }),
  })

  const canEdit = user?.role === 'admin' || user?.role === 'operator'
  const filtered = search
    ? tags.filter((t) =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.device.toLowerCase().includes(search.toLowerCase())
      )
    : tags

  const alarmLabel = (t: Tag) => {
    if (t.min_alarm == null && t.max_alarm == null) return '—'
    const parts: string[] = []
    if (t.min_alarm != null) parts.push(`${t.min_alarm}`)
    if (t.max_alarm != null) parts.push(`${t.max_alarm}`)
    return `${parts.join('–')}${t.unit ? ' ' + t.unit : ''}`
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Tag Yönetimi</h1>
        {canEdit && (
          <div className="flex gap-2">
            <button onClick={() => setShowFormat(true)} className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
              Format
            </button>
            <button onClick={() => setShowAdd(true)} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
              + Tag Ekle
            </button>
          </div>
        )}
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Tag veya cihaz adı ara..."
        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
      />

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-gray-500">Yükleniyor...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-gray-400">{search ? 'Eşleşen tag bulunamadı.' : 'Henüz tag yok.'}</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="border-b border-gray-800">
              <tr className="text-xs text-gray-500 uppercase tracking-wide">
                {['Cihaz', 'Tag Adı', 'Node ID', 'Birim', 'Alarm', 'Durum', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t: Tag) => (
                <tr key={t.id} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-sm text-gray-400">{t.device}</td>
                  <td className="px-4 py-3 text-sm font-medium text-white">{t.name}</td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500">{t.node_id}</td>
                  <td className="px-4 py-3 text-sm text-gray-300">{t.unit}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{alarmLabel(t)}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${t.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
                      {t.is_active ? 'Aktif' : 'Pasif'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canEdit && (
                      <div className="flex gap-3 justify-end">
                        <button onClick={() => setEditTag(t)} className="text-xs text-gray-500 hover:text-blue-400 transition-colors" title="Düzenle">✏</button>
                        <button onClick={() => delMut.mutate(t.id)} className="text-xs text-gray-500 hover:text-red-400 transition-colors" title="Sil">🗑</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAdd && <AddTagModal onClose={() => setShowAdd(false)} />}
      {showFormat && <FormatGuideModal onClose={() => setShowFormat(false)} />}
      {editTag && <EditTagModal tag={editTag} onClose={() => setEditTag(null)} />}
    </div>
  )
}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:5173/tags`. Verify:
- Search box filters tags by name or device
- ✏ opens the edit modal with pre-filled fields
- Setting `min_alarm=0, max_alarm=5000` and saving calls PATCH — row shows `0–5000 mm`
- Trying `min=5000, max=0` shows the validation error without sending the request
- 🗑 still deletes

- [ ] **Step 3: Commit**

```bash
git add src/pages/Tags.tsx
git commit -m "feat: tag search, edit modal with alarm thresholds, icon buttons"
```

---

## Task 8: Trend page — clear defaults, tag filter, dual Y-axis

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Trend.tsx`

- [ ] **Step 1: Replace `Trend.tsx` with updated version**

Full replacement of `scada-reporter/frontend/src/pages/Trend.tsx`:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTags, getTrend } from '../api/client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'

const COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#f87171', '#a78bfa', '#fb923c']
const HOURS = [
  { v: 1, l: 'Son 1 saat' },
  { v: 6, l: 'Son 6 saat' },
  { v: 24, l: 'Son 24 saat' },
  { v: 168, l: 'Son 7 gün' },
]

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-600 text-gray-200 text-sm px-4 py-3 rounded-xl shadow-xl z-50 flex items-center gap-3">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
    </div>
  )
}

export default function Trend() {
  const [selected, setSelected] = useState<number[]>([])
  const [hours, setHours] = useState(24)
  const [tagSearch, setTagSearch] = useState('')
  const [toast, setToast] = useState('')

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: series = [], isLoading } = useQuery({
    queryKey: ['trend', selected, hours],
    queryFn: () =>
      selected.length ? getTrend(selected, hours).then((r) => r.data) : Promise.resolve([]),
    enabled: selected.length > 0,
    refetchInterval: 30000,
  })

  const filteredTags = tagSearch
    ? tags.filter(
        (t) =>
          t.name.toLowerCase().includes(tagSearch.toLowerCase()) ||
          t.device.toLowerCase().includes(tagSearch.toLowerCase())
      )
    : tags

  // Determine Y-axis assignment by unit
  const selectedUnits: string[] = []
  const unitToAxis: Record<string, 'left' | 'right'> = {}
  series.forEach((s) => {
    if (!unitToAxis[s.unit]) {
      if (selectedUnits.length === 0) {
        unitToAxis[s.unit] = 'left'
        selectedUnits.push(s.unit)
      } else if (selectedUnits.length === 1 && !selectedUnits.includes(s.unit)) {
        unitToAxis[s.unit] = 'right'
        selectedUnits.push(s.unit)
      } else if (!selectedUnits.includes(s.unit)) {
        unitToAxis[s.unit] = 'left' // fallback (shouldn't reach — blocked in toggle)
      }
    }
  })

  const leftUnit = selectedUnits[0] ?? ''
  const rightUnit = selectedUnits[1] ?? ''

  const toggle = (id: number) => {
    if (selected.includes(id)) {
      setSelected((s) => s.filter((x) => x !== id))
      return
    }
    const tag = tags.find((t) => t.id === id)
    if (!tag) return
    const existingUnits = [...new Set(
      tags.filter((t) => selected.includes(t.id)).map((t) => t.unit)
    )]
    if (!existingUnits.includes(tag.unit) && existingUnits.length >= 2) {
      setToast('Maksimum 2 farklı birim. Önce mevcut bir birimi kaldır.')
      setTimeout(() => setToast(''), 4000)
      return
    }
    setSelected((s) => [...s, id])
  }

  // Merge all series into flat timeline for Recharts
  const timeline: Record<string, Record<string, number | string>> = {}
  series.forEach((s) => {
    s.data.forEach(({ t, v }) => {
      const key = format(parseISO(t), 'dd.MM HH:mm')
      timeline[key] ??= { t: key }
      timeline[key][s.name] = v
    })
  })
  const chartData = Object.values(timeline).sort((a, b) =>
    String(a.t).localeCompare(String(b.t))
  )

  const hasRightAxis = selectedUnits.length === 2

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Trend Grafik</h1>
        <div className="flex gap-2">
          {HOURS.map(({ v, l }) => (
            <button
              key={v}
              onClick={() => setHours(v)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                hours === v ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-4">
        {/* Tag selector */}
        <div className="w-52 bg-gray-900 border border-gray-800 rounded-xl p-3 flex-shrink-0 space-y-2">
          <input
            value={tagSearch}
            onChange={(e) => setTagSearch(e.target.value)}
            placeholder="Ara..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <p className="text-xs text-gray-500 uppercase tracking-wide px-1">Tag Seç</p>
          <div className="space-y-1">
            {filteredTags.length === 0 && (
              <p className="text-gray-500 text-xs px-1">Eşleşme yok.</p>
            )}
            {filteredTags.map((t, i) => {
              const colorIdx = tags.findIndex((x) => x.id === t.id)
              return (
                <button
                  key={t.id}
                  onClick={() => toggle(t.id)}
                  className={`w-full text-left px-2 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                    selected.includes(t.id)
                      ? 'bg-blue-600/20 text-blue-300'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: COLORS[colorIdx % COLORS.length] }}
                  />
                  <span className="truncate">{t.name}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Chart */}
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4">
          {selected.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Sol panelden tag seçin
            </div>
          ) : isLoading ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Yükleniyor...
            </div>
          ) : chartData.length === 0 ? (
            <div className="h-80 flex items-center justify-center text-gray-500 text-sm">
              Bu aralıkta veri yok.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={chartData} margin={{ top: 4, right: hasRightAxis ? 60 : 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#9ca3af' }} interval="preserveStartEnd" />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  width={55}
                  label={leftUnit ? { value: leftUnit, angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 11, offset: 10 } : undefined}
                />
                {hasRightAxis && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    width={55}
                    label={rightUnit ? { value: rightUnit, angle: 90, position: 'insideRight', fill: '#6b7280', fontSize: 11, offset: 10 } : undefined}
                  />
                )}
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#e5e7eb', fontSize: 12 }}
                  itemStyle={{ fontSize: 12 }}
                  formatter={(value, name) => {
                    const s = series.find((x) => x.name === name)
                    return [`${value} ${s?.unit ?? ''}`, name]
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
                {series.map((s, i) => (
                  <Line
                    key={s.tag_id}
                    type="monotone"
                    dataKey={s.name}
                    stroke={COLORS[i % COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    yAxisId={unitToAxis[s.unit] ?? 'left'}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:5173/trend`. Verify:
- No tags pre-selected on load
- Search box filters the tag list
- Selecting two tags with same unit (e.g. Hat1_Debi + Hat2_Debi, both m³/h) → single left Y-axis labeled `m³/h`
- Adding a bar-unit tag → second right Y-axis appears labeled `bar`
- Trying to add a 3rd different unit → toast appears
- Tooltip shows value + unit for each line

- [ ] **Step 3: Commit**

```bash
git add src/pages/Trend.tsx
git commit -m "feat: trend chart — clear defaults, tag filter, dual Y-axis by unit"
```

---

## Task 9: Reports page — grouped tag selection + history section

**Files:**
- Modify: `scada-reporter/frontend/src/pages/Reports.tsx`
- Modify: `scada-reporter/frontend/src/api/client.ts` (already done in Task 5 — imports available)

- [ ] **Step 1: Replace `Reports.tsx` with updated version**

Full replacement of `scada-reporter/frontend/src/pages/Reports.tsx`:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTags, generateReport, getReportHistory, downloadHistoryReport } from '../api/client'
import type { ReportHistoryEntry } from '../api/client'
import { format, subDays, startOfDay, endOfDay, parseISO } from 'date-fns'
import { tr } from 'date-fns/locale'

const fmt = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm")

const PRESETS = [
  { label: 'Bugün', start: () => startOfDay(new Date()), end: () => new Date() },
  { label: 'Dün', start: () => startOfDay(subDays(new Date(), 1)), end: () => endOfDay(subDays(new Date(), 1)) },
  { label: 'Son 7 Gün', start: () => startOfDay(subDays(new Date(), 7)), end: () => new Date() },
  { label: 'Son 30 Gün', start: () => startOfDay(subDays(new Date(), 30)), end: () => new Date() },
]

function HistoryRow({ entry }: { entry: ReportHistoryEntry }) {
  const [downloading, setDownloading] = useState(false)

  const reDownload = async () => {
    setDownloading(true)
    try {
      const r = await downloadHistoryReport(entry.id)
      const ext = entry.format === 'excel' ? 'xlsx' : 'json'
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `scada_rapor_${entry.id}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  const dateStr = format(parseISO(entry.created_at), 'dd.MM.yyyy HH:mm', { locale: tr })
  const tagCount = entry.tag_ids.length
  const rangeStart = format(parseISO(entry.start), 'dd.MM', { locale: tr })
  const rangeEnd = format(parseISO(entry.end), 'dd.MM', { locale: tr })

  return (
    <div className="flex items-center justify-between py-2.5 border-t border-gray-800">
      <div className="flex items-center gap-3">
        <span className="text-gray-500 text-sm">📄</span>
        <div>
          <span className="text-sm text-gray-300">{dateStr}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{tagCount} tag</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500">{rangeStart}–{rangeEnd}</span>
          <span className="text-gray-600 mx-2">·</span>
          <span className="text-xs text-gray-500 uppercase">{entry.format}</span>
        </div>
      </div>
      <button
        onClick={reDownload}
        disabled={downloading}
        className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 transition-colors"
      >
        {downloading ? '...' : '↓ İndir'}
      </button>
    </div>
  )
}

export default function Reports() {
  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => getTags().then((r) => r.data),
  })
  const { data: history = [], refetch: refetchHistory } = useQuery({
    queryKey: ['report-history'],
    queryFn: () => getReportHistory().then((r) => r.data),
  })

  const [selectedTags, setSelectedTags] = useState<number[]>([])
  const [start, setStart] = useState(fmt(startOfDay(new Date())))
  const [end, setEnd] = useState(fmt(new Date()))
  const [interval, setIntervalVal] = useState('hourly')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const toggleTag = (id: number) =>
    setSelectedTags((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])

  const selectPreset = (p: typeof PRESETS[0]) => {
    setStart(fmt(p.start()))
    setEnd(fmt(p.end()))
  }

  // Group tags by device
  const groups = tags.reduce<Record<string, typeof tags>>((acc, t) => {
    const key = t.device || 'Diğer';
    (acc[key] ??= []).push(t)
    return acc
  }, {})

  const toggleGroup = (groupTags: typeof tags) => {
    const ids = groupTags.map((t) => t.id)
    const allSelected = ids.every((id) => selectedTags.includes(id))
    if (allSelected) {
      setSelectedTags((s) => s.filter((id) => !ids.includes(id)))
    } else {
      setSelectedTags((s) => [...new Set([...s, ...ids])])
    }
  }

  const download = async (outputFormat: 'excel' | 'json') => {
    if (!selectedTags.length) { setError('En az bir tag seçin'); return }
    setError(''); setLoading(true)
    try {
      const r = await generateReport({
        tag_ids: selectedTags, start, end, interval, format: outputFormat,
      })
      if (outputFormat === 'excel') {
        const url = URL.createObjectURL(new Blob([r.data]))
        const a = document.createElement('a')
        a.href = url
        a.download = `scada_rapor_${start.slice(0, 10)}_${end.slice(0, 10)}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      }
      refetchHistory()
    } catch {
      setError('Rapor oluşturulamadı.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-xl font-bold text-white">Rapor Oluştur</h1>

      {/* Grouped tag selection */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-300">Tag Seçimi</p>
          <span className="text-xs text-gray-500">{selectedTags.length} tag seçili</span>
        </div>
        {Object.entries(groups).map(([device, groupTags]) => {
          const allSelected = groupTags.every((t) => selectedTags.includes(t.id))
          return (
            <div key={device}>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{device}</span>
                <button
                  onClick={() => toggleGroup(groupTags)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {allSelected ? 'Tümünü Kaldır' : 'Tümünü Seç'}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {groupTags.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => toggleTag(t.id)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      selectedTags.includes(t.id)
                        ? 'bg-blue-600/20 border-blue-500 text-blue-300'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {t.name}{t.unit ? ` (${t.unit})` : ''}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Time range */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">Zaman Aralığı</p>
        <div className="flex gap-2 flex-wrap">
          {PRESETS.map((p) => (
            <button key={p.label} onClick={() => selectPreset(p)}
              className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors">
              {p.label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Başlangıç</label>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Bitiş</label>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Grouping */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <p className="text-sm font-medium text-gray-300">Gruplama</p>
        <div className="flex gap-2">
          {[{ v: 'hourly', l: 'Saatlik' }, { v: 'daily', l: 'Günlük' }].map(({ v, l }) => (
            <button key={v} onClick={() => setIntervalVal(v)}
              className={`px-4 py-2 text-sm rounded-lg border transition-colors ${
                interval === v
                  ? 'bg-blue-600/20 border-blue-500 text-blue-300'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Download buttons */}
      <div className="flex gap-3">
        <button onClick={() => download('excel')} disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {loading ? 'Hazırlanıyor...' : 'Excel İndir'}
        </button>
        <button onClick={() => download('json')} disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg font-medium text-sm border border-gray-700 transition-colors">
          JSON
        </button>
      </div>

      {/* Report history */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <p className="text-sm font-medium text-gray-300 mb-1">Son Raporlar</p>
        {history.length === 0 ? (
          <p className="text-gray-500 text-sm py-4">Henüz rapor oluşturulmadı.</p>
        ) : (
          history.map((entry) => <HistoryRow key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:5173/reports`. Verify:
- Tags grouped by device with "Tümünü Seç" / "Tümünü Kaldır" button per group
- "X tag seçili" count updates
- "Format ?" button is gone
- Generating a report adds an entry to the history section below
- "↓ İndir" re-downloads the report

- [ ] **Step 3: Compile check**

```bash
cd scada-reporter/frontend
pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Reports.tsx
git commit -m "feat: reports grouped tag selection and download history section"
```

---

## Task 10: Final integration check

- [ ] **Step 1: Run full backend test suite**

```bash
cd scada-reporter/backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Start both servers, do a full manual walkthrough**

```bash
# Terminal 1
cd scada-reporter/backend && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2
cd scada-reporter/frontend && pnpm dev
```

Checklist:
- [ ] Dashboard: 4 stat cards, PLC Bağlantı shows green, Havuz_Seviye row red + OVERFLOW text
- [ ] Dashboard: alarm banner visible with Havuz_Seviye link; clicking scrolls to row; ✕ dismisses
- [ ] Tags: search filters by name and device
- [ ] Tags: ✏ opens edit modal; setting min/max alarm saves and shows in Alarm column
- [ ] Tags: min > max shows validation error without sending request
- [ ] Trend: page loads with no pre-selected tags
- [ ] Trend: search filters tag list
- [ ] Trend: two same-unit tags → single Y-axis labeled with unit
- [ ] Trend: adding different-unit tag → right Y-axis appears
- [ ] Trend: attempting 3rd unit → toast message
- [ ] Reports: tags grouped by device with "Tümünü Seç"
- [ ] Reports: "Format ?" button gone
- [ ] Reports: generating report → entry appears in history
- [ ] Reports: "↓ İndir" re-downloads saved report

- [ ] **Step 3: Push branch**

```bash
cd C:/project/smart
git push origin feat/frontend-and-cert-utils
```
