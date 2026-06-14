import json
import os
import uuid
from datetime import datetime
from io import BytesIO

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.report_history import ReportHistory
from app.models.tag import Tag, TagReading

router = APIRouter(prefix="/reports", tags=["reports"])

REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)  # Safeguard for test runs


class ReportRequest(BaseModel):
    tag_ids: list[int]
    start: datetime
    end: datetime
    interval: str = "hourly"  # "hourly" | "daily"
    format: str = "excel"  # "excel" | "json"


async def _fetch_aggregated(
    tag_ids: list[int], start: datetime, end: datetime, interval: str, db: AsyncSession
) -> dict:
    """Tag verilerini istenilen interval'de gruplara ayırır."""
    if interval == "daily":
        period_expr = func.strftime("%Y-%m-%d", TagReading.timestamp)
    else:
        period_expr = func.strftime("%Y-%m-%d %H:00", TagReading.timestamp)

    result = await db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.unit,
            period_expr.label("period"),
            func.avg(TagReading.value).label("avg_val"),
            func.min(TagReading.value).label("min_val"),
            func.max(TagReading.value).label("max_val"),
            func.count(TagReading.timestamp).label("count"),
        )
        .join(TagReading, Tag.id == TagReading.tag_id)
        .where(
            Tag.id.in_(tag_ids),
            TagReading.timestamp >= start,
            TagReading.timestamp <= end,
        )
        .group_by(Tag.id, Tag.name, Tag.unit, "period")
        .order_by(Tag.name, "period")
    )
    rows = result.all()

    data: dict[str, list] = {}
    for _tag_id, name, unit, period, avg, mn, mx, cnt in rows:
        key = f"{name} ({unit})" if unit else name
        if key not in data:
            data[key] = []
        data[key].append(
            {
                "period": period,
                "avg": round(avg, 3) if avg else None,
                "min": round(mn, 3) if mn else None,
                "max": round(mx, 3) if mx else None,
                "count": cnt,
            }
        )
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
    await db.flush()  # get the ID

    # Keep only the 10 most recent
    result = await db.execute(select(ReportHistory).order_by(ReportHistory.created_at.asc()))
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
        payload = {
            "period": req.interval,
            "start": str(req.start),
            "end": str(req.end),
            "data": data,
        }
        file_path = os.path.join(REPORTS_DIR, f"{file_id}.json")
        os.makedirs(REPORTS_DIR, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str)
        await _save_history(req, file_path, db)
        return payload

    # Excel raporu
    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = "Ozet"

    ws_summary["A1"] = "SCADA Raporu"
    ws_summary["A2"] = f"Baslangic: {req.start.strftime('%d.%m.%Y %H:%M')}"
    ws_summary["A3"] = f"Bitis: {req.end.strftime('%d.%m.%Y %H:%M')}"
    ws_summary["A4"] = f"Interval: {req.interval}"

    for tag_name, rows in data.items():
        ws = wb.create_sheet(title=tag_name[:31])
        ws.append(["Donem", "Ortalama", "Minimum", "Maksimum", "Okuma Sayisi"])
        for row in rows:
            ws.append(
                [
                    row["period"] if row["period"] else "",
                    row["avg"],
                    row["min"],
                    row["max"],
                    row["count"],
                ]
            )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    file_path = os.path.join(REPORTS_DIR, f"{file_id}.xlsx")
    os.makedirs(REPORTS_DIR, exist_ok=True)
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
async def list_history(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """List last 10 generated reports."""
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
    """Download a previously generated report by history ID."""
    result = await db.execute(select(ReportHistory).where(ReportHistory.id == history_id))
    record = result.scalar_one_or_none()
    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")
    return FileResponse(record.file_path)
