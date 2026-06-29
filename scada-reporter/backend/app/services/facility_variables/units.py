"""Muhafazakâr birim uyumluluk uyarısı (v1: yalnız uyar, asla engelleme).

add/sub: operandların birimleri farklı ve ikisi de boş değilse uyar. mul/div
birimleri meşru biçimde değiştirir → uyarmaz. Bilinmeyen/boş birim → uyarmaz.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag


async def _leaf_unit(db: AsyncSession, node: dict) -> str | None:
    """Bir düğümün taşıdığı birim (çözülebiliyorsa). Aritmetikte ilk somut birim."""
    op = node.get("op")
    if op in ("agg", "series"):
        src = node.get("source") or {}
        if src.get("type") == "tag":
            result = await db.execute(select(Tag).where(Tag.id == src.get("tag_id")))
            tag = result.scalar_one_or_none()
            return tag.unit if tag and tag.unit else None
        return None
    if op == "ref":
        var = await db.get(FacilityVariable, node.get("variable_id"))
        return var.unit if var and var.unit else None
    if op in ("round", "abs"):
        return await _leaf_unit(db, node.get("source") or {})
    if op in ("add", "sub", "coalesce"):
        for a in node.get("args", []):
            u = await _leaf_unit(db, a)
            if u:
                return u
    return None


async def unit_warnings(db: AsyncSession, expression: dict) -> list[str]:
    warns: list[str] = []
    await _walk(db, expression, warns)
    return warns


async def _walk(db: AsyncSession, node: object, warns: list[str]) -> None:
    if not isinstance(node, dict):
        return
    op = node.get("op")
    if op in ("add", "sub"):
        units = []
        for a in node.get("args", []):
            u = await _leaf_unit(db, a)
            if u:
                units.append(u)
        distinct = set(units)
        if len(distinct) > 1:
            warns.append(f"{op}: uyumsuz birimler {sorted(distinct)} — sonuç anlamsız olabilir")
    for a in node.get("args", []):
        await _walk(db, a, warns)
    if "source" in node:
        await _walk(db, node["source"], warns)
