"""Excel sütununu değere çözer: tag → daily_values, variable → engine.

Çıktı şekli sözleşmesi (Plan 1): kolon hedefi {gün_no: değer}, hücre hedefi tek
scalar. Verisi olmayan gün anahtarsız (0 uydurma yok). Pasif/eksik değişken
sessiz boş yazmaz — görünür uyarı döndürür.
"""

from __future__ import annotations

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
