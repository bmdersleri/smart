"""Tesis değişkeni servis katmanı: CRUD, bağımlılık saklama, döngü reddi."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.excel_template import ExcelTemplateColumn
from app.models.facility_variable import FacilityVariable, FacilityVariableDependency
from app.services.facility_variables.expression import (
    ExpressionError,
    extract_dependencies,
    validate_expression,
)

# version'ı artıran alanlar (kozmetik olmayanlar).
_VERSION_FIELDS = ("expression_json", "null_policy", "quality_policy", "default_time_grain")


class VariableError(ValueError):
    """Doğrulama veya döngü hatası."""


async def would_create_cycle(db: AsyncSession, var_id: int | None, dep_var_ids: list[int]) -> bool:
    """dep_var_ids'den var_id'ye ulaşan bir yol varsa True (döngü)."""
    if var_id is None:
        return False
    # Bağımlılık grafiğini variable→variable kenarları üzerinden gez.
    rows = await db.execute(
        select(
            FacilityVariableDependency.variable_id,
            FacilityVariableDependency.depends_on_variable_id,
        ).where(FacilityVariableDependency.depends_on_type == "variable")
    )
    edges: dict[int, list[int]] = {}
    for src, dst in rows.all():
        if dst is not None:
            edges.setdefault(src, []).append(dst)

    stack = list(dep_var_ids)
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur == var_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(edges.get(cur, []))
    return False


async def _store_dependencies(db: AsyncSession, var: FacilityVariable, expression: dict) -> None:
    deps = extract_dependencies(expression)
    dep_var_ids = [vid for (t, _tid, vid) in deps if t == "variable" and vid is not None]
    if await would_create_cycle(db, var.id, dep_var_ids):
        raise VariableError("Bağımlılık döngüsü (cycle) reddedildi")
    # Mevcut bağımlılıkları temizle, yenilerini yaz.
    await db.refresh(var, attribute_names=["dependencies"])
    var.dependencies.clear()
    for dtype, tag_id, variable_id in deps:
        var.dependencies.append(
            FacilityVariableDependency(
                depends_on_type=dtype,
                depends_on_tag_id=tag_id,
                depends_on_variable_id=variable_id,
            )
        )


async def create_variable(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    description: str,
    kind: str,
    unit: str,
    expression: dict,
    null_policy: str,
    quality_policy: str,
    default_time_grain: str | None,
    value_type: str,
    created_by: int | None,
) -> FacilityVariable:
    try:
        validate_expression(expression, kind)
    except ExpressionError as e:
        raise VariableError(str(e)) from e

    var = FacilityVariable(
        code=code,
        name=name,
        description=description,
        kind=kind,
        value_type=value_type,
        unit=unit,
        expression_json=json.dumps(expression),
        null_policy=null_policy,
        quality_policy=quality_policy,
        default_time_grain=default_time_grain,
        version=1,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(var)
    await db.flush()  # var.id gerekli (bağımlılıklar için)
    await _store_dependencies(db, var, expression)
    await db.commit()
    await db.refresh(var)
    return var


async def update_variable(
    db: AsyncSession,
    var_id: int,
    *,
    name: str,
    description: str,
    unit: str,
    expression: dict,
    null_policy: str,
    quality_policy: str,
    default_time_grain: str | None,
    updated_by: int | None,
) -> FacilityVariable:
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise VariableError("Değişken bulunamadı")
    try:
        validate_expression(expression, var.kind)
    except ExpressionError as e:
        raise VariableError(str(e)) from e

    # Compute bump using OLD field values BEFORE any mutation.
    new_expr = json.dumps(expression)
    bump = (
        new_expr != var.expression_json
        or null_policy != var.null_policy
        or quality_policy != var.quality_policy
        or default_time_grain != var.default_time_grain
    )
    # Cycle check runs inside _store_dependencies BEFORE it mutates var.dependencies.
    # Call it now so that a VariableError raised here leaves all scalar fields untouched.
    await _store_dependencies(db, var, expression)
    # Only mutate scalar fields after the cycle check has passed.
    var.name = name
    var.description = description
    var.unit = unit
    var.expression_json = new_expr
    var.null_policy = null_policy
    var.quality_policy = quality_policy
    var.default_time_grain = default_time_grain
    var.updated_by = updated_by
    if bump:
        var.version += 1
    await db.commit()
    await db.refresh(var)
    return var


async def columns_referencing_variable(db: AsyncSession, var_id: int) -> list[ExcelTemplateColumn]:
    """var_id'ye bağlı, etkin Excel sütunları."""
    rows = await db.execute(
        select(ExcelTemplateColumn).where(
            ExcelTemplateColumn.source_type == "variable",
            ExcelTemplateColumn.variable_id == var_id,
            ExcelTemplateColumn.enabled.is_(True),
        )
    )
    return list(rows.scalars().all())


async def deactivate_variable(
    db: AsyncSession, var_id: int, *, force: bool = False
) -> FacilityVariable:
    var = await db.get(FacilityVariable, var_id)
    if var is None:
        raise VariableError("Değişken bulunamadı")
    if not force:
        refs = await columns_referencing_variable(db, var_id)
        if refs:
            tpl_ids = sorted({c.template_id for c in refs})
            raise VariableError(
                f"Değişken Excel şablonlarınca kullanılıyor (template {tpl_ids}); "
                "önce bağlamayı kaldırın veya force kullanın"
            )
    var.is_active = False
    await db.commit()
    await db.refresh(var)
    return var
