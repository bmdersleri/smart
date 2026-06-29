"""Bir tesis değişkenini değerlendirir, ref'leri aktif değişkenlere çözer.

preview ve Excel binding ortak bu giriş noktasını kullanır — iki ayrı ref
çözüm yolu olmasın (sapma riski). Saklanan değişkenler döngüsüzdür (döngü
yazma anında reddedilir), bu yüzden özyineleme sonlanır.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.services.facility_variables.engine import EvalResult, evaluate


async def evaluate_variable(
    db: AsyncSession,
    var: FacilityVariable,
    *,
    start: datetime,
    end: datetime,
    grain: str,
    tz_offset_hours: int,
) -> EvalResult:
    expression = json.loads(var.expression_json)

    async def resolve_ref(variable_id: int) -> EvalResult:
        ref_var = await db.get(FacilityVariable, variable_id)
        if ref_var is None or not ref_var.is_active:
            return EvalResult(kind="scalar", scalar=None)
        return await evaluate_variable(
            db, ref_var, start=start, end=end, grain=grain, tz_offset_hours=tz_offset_hours
        )

    return await evaluate(
        db,
        expression,
        start=start,
        end=end,
        grain=grain,
        tz_offset_hours=tz_offset_hours,
        resolve_ref=resolve_ref,
    )
