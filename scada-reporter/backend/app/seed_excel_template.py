"""Günlük rapor Excel şablonunu + kolon bağlamalarını idempotent ekler.

Operatör gerçek çalışma kitabını `app/seed_data/gunluk_rapor.xlsx` olarak commit
etmeli. Şablon adı benzersizdir; varsa atlanır.

Bağlamalar gerçek `gunluk_rapor.xlsx` HAZİRAN-tipi aylık sayfasına göre ayarlanmıştır
(başlık satırları 1-4, veri 5. satırdan, tarih kolonu D):

- **Günlük ham totalizer kolonları → doğrudan TAG** (`TAG_COLUMN_BINDINGS`). Bunlar
  her gün için bir değer ister; scalar değişken günlük kolon dolduramaz (binding
  `_is_cell_target`: `var.kind=="scalar"` → hücre hedefi), bu yüzden tag+agg ile
  `daily_values` üzerinden per-gün doldurulur.
- **Türetilmiş kolonlar K (=I+J), M (=E+K+F)** sayfanın KENDİ formülleridir —
  bağlanmaz, I/J dolunca Excel kendi hesaplar.
- **Özet-hücre değişken kolonları** (`VARIABLE_COLUMN_BINDINGS`) opsiyoneldir; scalar
  değişken tek bir hücreye yazılır (`target_mode="cell"` + `target_cell` ŞART).
  Varsayılan boş — örnek için aşağıdaki yoruma bakın.

Tarih kolonu sayfada formüldür (`=D5+1`); `date_mode="write"` ZORUNLU — `match` modu
yalnız literal datetime hücrelerini tanır, formülleri atlar.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.excel_template import ExcelTemplate, ExcelTemplateColumn
from app.models.tag import Tag
from app.seed_facility_variables import seed_variables

TEMPLATE_NAME = "Günlük Rapor Şablonu"
WORKBOOK_PATH = Path(__file__).parent / "seed_data" / "gunluk_rapor.xlsx"

# Çalışma sayfası geometrisi — gerçek gunluk_rapor.xlsx aylık sayfasına göre.
# sheet_name fill_template'in yazacağı SABİT sayfadır; hedef aya göre değiştirin
# (kitap aylık çok-sayfalı arşivdir; tek-sayfalı temiz şablon idealdir).
SHEET_META = dict(
    sheet_name="HAZİRAN 2026", header_row=2, date_col="D", data_start_row=5, date_mode="write"
)

# Günlük ham totalizer kolonları → (kolon_harfi, tag node_id, agg). Per-gün doldurulur.
TAG_COLUMN_BINDINGS: list[tuple[str, str, str]] = [
    ("I", "gtuTP02DB01.GUNLUK", "last"),  # Terfi 1 çıkış debi (günlük)
    ("J", "gtuTP01DB01.GUNLUK", "last"),  # Terfi 2 çıkış debi (günlük)
]

# Opsiyonel özet-hücre değişken kolonları → (kolon_harfi, değişken_kodu, target_cell).
# Scalar değişkenler tek hücreye yazılır. Örn. aylık AÖT toplamını bir özet hücreye:
#   ("E", "aot_giris_debi_gunluk", "E40"),
# Varsayılan boş bırakıldı — operatör gerçek özet hücrelerine göre doldurur.
VARIABLE_COLUMN_BINDINGS: list[tuple[str, str, str]] = []


async def _resolve_tag(db: AsyncSession, node_id: str) -> int | None:
    """node_id → Tag.id; yoksa None (kolon atlanır, hata değil)."""
    return (await db.execute(select(Tag.id).where(Tag.node_id == node_id))).scalar_one_or_none()


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

    # Günlük ham totalizer kolonları → doğrudan tag (per-gün daily_values).
    for col_letter, node_id, agg in TAG_COLUMN_BINDINGS:
        tag_id = await _resolve_tag(db, node_id)
        if tag_id is None:
            print(f"  UYARI: {col_letter} → tag {node_id} katalogda yok, atlandı")
            continue
        columns.append(
            ExcelTemplateColumn(
                col_letter=col_letter,
                source_type="tag",
                variable_id=None,
                write_mode=None,
                reduce_op=None,
                target_mode="column",
                target_cell=None,
                variable_code_snapshot=None,
                tag_id=tag_id,
                agg=agg,
                source_code=node_id,
                enabled=True,
            )
        )

    # Opsiyonel özet-hücre değişken kolonları → scalar değişken, target_cell şart.
    for col_letter, var_code, target_cell in VARIABLE_COLUMN_BINDINGS:
        var_id = code_to_id.get(var_code)
        if var_id is None:
            print(f"  UYARI: {col_letter} → {var_code} değişkeni yok, atlandı (env eksik olabilir)")
            continue
        columns.append(
            ExcelTemplateColumn(
                col_letter=col_letter,
                source_type="variable",
                variable_id=var_id,
                write_mode="reduce",
                reduce_op="last",
                target_mode="cell",
                target_cell=target_cell,
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
        code_to_id = await seed_variables(db)  # özet-hücre bağlamaları için değişkenleri garanti et
        await seed_excel_template(db, code_to_id=code_to_id)


if __name__ == "__main__":
    asyncio.run(main())
