"""Günlük rapor Excel şablonunu + kolon→değişken bağlamalarını idempotent ekler.

Operatör gerçek çalışma kitabını `app/seed_data/gunluk_rapor.xlsx` olarak commit
etmeli. Şablon adı benzersizdir; varsa atlanır. Kolon haritası tasarım dokümanının
varsayılanıdır (E/F/K/M) — gerçek sayfaya göre düzenleyin.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.seed_facility_variables import seed_variables

TEMPLATE_NAME = "Günlük Rapor Şablonu"
WORKBOOK_PATH = Path(__file__).parent / "seed_data" / "gunluk_rapor.xlsx"

# Çalışma sayfası geometrisi — gerçek kitaba göre ayarlayın.
SHEET_META = dict(
    sheet_name="OCAK", header_row=2, date_col="D", data_start_row=5, date_mode="write"
)

# Kolon harfi -> değişken kodu (tasarım §510-515 varsayılanı)
COLUMN_BINDINGS: list[tuple[str, str]] = [
    ("E", "aot_giris_debi_gunluk"),
    ("F", "kapasite_fazlasi_gunluk"),
    ("K", "baat_giris_debi_gunluk"),
    ("M", "tesis_toplam_debi_hesaplanan_gunluk"),
]


async def seed_excel_template(db: AsyncSession, *, code_to_id: dict[str, int]) -> int | None:
    """Şablon + bağlamaları ekler. Zaten varsa (ada göre) atlar, mevcut id döner.

    Çalışma kitabı yoksa da None döner.
    """
    if not WORKBOOK_PATH.exists():
        print(
            f"  ATLA: çalışma kitabı yok: {WORKBOOK_PATH}"
            " — gerçek gunluk_rapor.xlsx'i buraya commit edin"
        )
        return None

    existing = await db.execute(select(ExcelTemplate.id).where(ExcelTemplate.name == TEMPLATE_NAME))
    found = existing.scalar_one_or_none()
    if found is not None:
        print(f"  skip (şablon var): {TEMPLATE_NAME} (id={found})")
        return found

    blob = WORKBOOK_PATH.read_bytes()
    tpl = ExcelTemplate(
        name=TEMPLATE_NAME,
        description="Tesis günlük debi raporu (seed)",
        file_blob=blob,
        created_by=None,
        **SHEET_META,
    )

    columns: list[ExcelTemplateColumn] = []
    for col_letter, var_code in COLUMN_BINDINGS:
        var_id = code_to_id.get(var_code)
        if var_id is None:
            print(
                f"  UYARI: {col_letter} → {var_code} değişkeni yok, kolon atlandı"
                " (env eksik olabilir)"
            )
            continue
        columns.append(
            ExcelTemplateColumn(
                col_letter=col_letter,
                source_type="variable",
                variable_id=var_id,
                write_mode="reduce",
                reduce_op="last",
                target_mode="column",
                target_cell=None,
                variable_code_snapshot=var_code,
                tag_id=None,
                agg="last",
                source_code=var_code,
                enabled=True,
            )
        )
    tpl.columns = columns
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    print(f"  + şablon {TEMPLATE_NAME} (id={tpl.id}), {len(columns)} kolon bağlandı")
    return tpl.id


async def main() -> None:
    async with AsyncSessionLocal() as db:
        code_to_id = await seed_variables(db)  # değişkenleri garanti et
        await seed_excel_template(db, code_to_id=code_to_id)


if __name__ == "__main__":
    asyncio.run(main())
