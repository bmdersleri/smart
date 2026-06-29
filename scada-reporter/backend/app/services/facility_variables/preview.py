"""Önizleme katmanı: sınırlı pencere değerlendirmesi + ref özyineleme + tz'li ts.

Cache yok (v1) → pencere sert sınırlanır, aksi halde UI tetikli DB DoS.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.resolver import evaluate_variable

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
            f"Önizleme çok geniş: > {MAX_PREVIEW_POINTS} nokta. "
            "Pencereyi daralt veya grain'i büyüt."
        )


def _iso_offset(dt: datetime, tz_offset_hours: int) -> str:
    tz = timezone(timedelta(hours=tz_offset_hours))
    return dt.replace(tzinfo=tz).isoformat()


def serialize_eval_result(result, unit: str, tz_offset_hours: int) -> dict:
    """EvalResult -> önizleme/rapor için ortak JSON şekli (tek serileştirme yolu)."""
    if result.kind == "scalar":
        return {"kind": "scalar", "value": result.scalar, "unit": unit}
    points = [
        {"ts": _iso_offset(k, tz_offset_hours), "value": v}
        for k, v in sorted((result.series or {}).items())
    ]
    return {"kind": "series", "points": points, "unit": unit}


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

    result = await evaluate_variable(
        db, var, start=start, end=end, grain=grain, tz_offset_hours=tz_offset_hours
    )

    return serialize_eval_result(result, var.unit, tz_offset_hours)
