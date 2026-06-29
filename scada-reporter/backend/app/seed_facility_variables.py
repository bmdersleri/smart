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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.facility_variable import FacilityVariable
from app.models.tag import Tag
from app.services.facility_variables.service import VariableError, create_variable


async def resolve_tag_id(db: AsyncSession, node_id: str) -> int:
    """node_id'den Tag.id döndürür; yoksa anlaşılır hata verir."""
    row = await db.execute(select(Tag.id).where(Tag.node_id == node_id))
    tag_id = row.scalar_one_or_none()
    if tag_id is None:
        raise RuntimeError(f"Katalogda tag yok: {node_id!r} — önce `just seed-catalog` çalıştırın")
    return tag_id


def _agg(tag_id: int, agg: str, window: str = "day") -> dict:
    return {"op": "agg", "source": {"type": "tag", "tag_id": tag_id}, "agg": agg, "window": window}


async def seed_variables(db: AsyncSession) -> dict[str, int]:
    """Çekirdek + (env varsa) BAAT/kapasite/kompozit değişkenleri ekler.

    Döner: {code: variable_id} — tüm oluşturulan VEYA zaten var olan değişkenler.
    Bağımlılık sırasına göre eklenir (ref-kompozitler sonra)."""
    terfi1 = await resolve_tag_id(db, "gtuTP02DB01.GUNLUK")  # Terfi 1 günlük totalizer
    terfi2 = await resolve_tag_id(db, "gtuTP01DB01.GUNLUK")  # Terfi 2 günlük totalizer
    genel = await resolve_tag_id(db, "GENEL_TOPLAM_DEBI")  # kümülatif grand total

    existing = await db.execute(select(FacilityVariable.code, FacilityVariable.id))
    code_to_id: dict[str, int] = {c: i for c, i in existing.all()}

    async def ensure(
        *,
        code: str,
        expression: dict,
        kind: str,
        name: str,
        description: str,
        unit: str = "m3/gün",
        grain: str | None = "day",
    ) -> None:
        if code in code_to_id:
            print(f"  skip (var): {code}")
            return
        try:
            var = await create_variable(
                db,
                code=code,
                name=name,
                description=description,
                kind=kind,
                unit=unit,
                value_type="number",
                expression=expression,
                null_policy="skip",
                quality_policy="good_only",
                default_time_grain=grain,
                created_by=None,
            )
            code_to_id[code] = var.id
            print(f"  + {code} (id={var.id})")
        except IntegrityError as exc:
            await db.rollback()
            print(f"  HATA {code}: {exc}")
        except VariableError as exc:
            print(f"  HATA {code}: {exc}")

    # --- Çekirdek (her zaman, gerçek tag'ler) ---
    await ensure(
        code="terfi1_debi_gunluk",
        kind="scalar",
        name="Terfi 1 Çıkış Debi (Günlük)",
        description="Terfi 1 günlük totalizer son değeri",
        expression=_agg(terfi1, "last"),
    )
    await ensure(
        code="terfi2_debi_gunluk",
        kind="scalar",
        name="Terfi 2 Çıkış Debi (Günlük)",
        description="Terfi 2 günlük totalizer son değeri",
        expression=_agg(terfi2, "last"),
    )
    await ensure(
        code="aot_giris_debi_gunluk",
        kind="scalar",
        name="AÖT Tesise Alınan Debi (Günlük)",
        description="Terfi 1 + Terfi 2 günlük debisi toplamı",
        expression={"op": "add", "args": [_agg(terfi1, "last"), _agg(terfi2, "last")]},
    )
    await ensure(
        code="tesis_toplam_debi_olculen_gunluk",
        kind="scalar",
        name="Tesis Toplam Debi — Ölçülen (Günlük)",
        description="GENEL_TOPLAM_DEBI kümülatif totalizer günlük delta'sı",
        expression=_agg(genel, "delta"),
    )
    # 7-günlük ortalama giriş debisi: günlük delta serisini 7d penceresinde ortala
    await ensure(
        code="giris_7gun_ort_debi",
        kind="scalar",
        name="Giriş Debi — 7 Günlük Ortalama",
        description="GENEL_TOPLAM_DEBI günlük delta serisinin son 7 gün ortalaması",
        expression={
            "op": "reduce",
            "reduce": "avg",
            "source": {
                "op": "series",
                "source": {"type": "tag", "tag_id": genel},
                "agg": "delta",
                "grain": "day",
                "window": "7d",
            },
        },
    )

    # --- Opsiyonel (deployment config) — Task 2 doldurur ---
    await _seed_optional(db, ensure, code_to_id)

    await db.commit()
    return code_to_id


async def _seed_optional(db, ensure, code_to_id: dict[str, int]) -> None:
    """BAAT / kapasite / kompozit — env yoksa atlanır. Task 2'de doldurulacak."""
    return  # Task 2'de doldurulacak


async def main() -> None:
    async with AsyncSessionLocal() as db:
        created = await seed_variables(db)
        print(f"Bitti: {len(created)} değişken (oluşturulan+mevcut)")


if __name__ == "__main__":
    asyncio.run(main())
