from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from io import BytesIO
import openpyxl
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.tag import Tag, TagReading

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    tag_ids: list[int]
    start: datetime
    end: datetime
    interval: str = "hourly"  # hourly, daily
    format: str = "excel"  # excel, json


async def _fetch_aggregated(
    tag_ids: list[int], start: datetime, end: datetime, interval: str, db: AsyncSession
) -> dict:
    """Tag verilerini istenilen interval'de gruplara ayırır."""
    # SQLite ve PostgreSQL uyumlu strftime tabanlı gruplama
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
    for tag_id, name, unit, period, avg, mn, mx, cnt in rows:
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


@router.post("/generate")
async def generate_report(
    req: ReportRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    data = await _fetch_aggregated(req.tag_ids, req.start, req.end, req.interval, db)

    if req.format == "json":
        return {
            "period": req.interval,
            "start": req.start,
            "end": req.end,
            "data": data,
        }

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

    filename = (
        f"scada_rapor_{req.start.strftime('%Y%m%d')}_{req.end.strftime('%Y%m%d')}.xlsx"
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
