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
