"""WinCC export'larından uzun-süre (archive) tag kataloğunu veritabanına yükler.

Kullanım:
    python -m app.seed_catalog            # archive tag'lerini ekle (mevcutları atla)
    python -m app.seed_catalog --reset    # önce tüm tag'leri sil, sonra ekle

xlsx dosyaları repo kökündeki `xlsx/` klasöründen okunur:
    - full_export.xlsx: Tam WinCC kataloğu
    - archive_export.xlsx: Arşiv tag'leri tanımları
    - gunluk_rapor.xlsx: Günlük raporlar (isteğe bağlı)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.import_catalog import build_archive_catalog
from app.models.tag import Tag, TagReading

XLSX_DIR = Path(__file__).resolve().parents[3] / "xlsx"
FULL = XLSX_DIR / "full_export.xlsx"
ARCHIVE = XLSX_DIR / "archive_export.xlsx"
GUNLUK = XLSX_DIR / "gunluk_rapor.xlsx"


async def main(reset: bool = False) -> None:
    for p in (FULL, ARCHIVE):
        if not p.exists():
            print(f"HATA: {p} bulunamadi")
            return

    has_gunluk = GUNLUK.exists()
    print(f"Okunuyor: {FULL.name} + {ARCHIVE.name}" + (f" + {GUNLUK.name}" if has_gunluk else ""))
    result = build_archive_catalog(str(FULL), str(ARCHIVE), str(GUNLUK) if has_gunluk else None)
    print(f"Cozuldu: {result.resolved} tag | Atlandi (S7 degil): {result.skipped}")
    if result.skipped_names:
        print(f"  Atlanan ornekler: {', '.join(result.skipped_names[:5])} ...")
    print(
        f"Gunluk takip eslesen: {result.daily_matched} | "
        f"eslesmeyen token: {len(result.daily_unmatched)}"
    )
    if result.daily_unmatched:
        print(f"  Eslesmeyen token ornekleri: {', '.join(result.daily_unmatched[:8])}")

    async with AsyncSessionLocal() as db:
        if reset:
            await db.execute(delete(TagReading))
            await db.execute(delete(Tag))
            await db.commit()
            print("Mevcut tum tag'ler ve okumalar silindi (--reset)")

        existing = await db.execute(select(Tag.node_id))
        existing_ids = {r[0] for r in existing.all()}

        added = 0
        skipped_dupe = 0
        for t in result.tags:
            if t["node_id"] in existing_ids:
                skipped_dupe += 1
                continue
            db.add(Tag(**t))
            existing_ids.add(t["node_id"])
            added += 1
        if added:
            await db.commit()
        print(f"Eklendi: {added} | Zaten vardi: {skipped_dupe}")


if __name__ == "__main__":
    asyncio.run(main(reset="--reset" in sys.argv))
