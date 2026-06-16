"""Tag tiplerine göre toplu deadband (report-by-exception) ayarı.

Birim metadatası yok; tip için ``data_type`` + son GOOD okumanın büyüklüğü
kullanılır. Sürekli değer yerine birkaç **tier** atanır (tipik tag tipleri):

- Binary / Unsigned (ayrık sinyaller) -> deadband YOK (durum değişimi zaten
  kalite/değer değişimiyle yazılır).
- Float (analog) -> büyüklük tier'ı: <10 ->0.1, <100 ->0.5, <1k ->2,
  <100k ->10, >=100k ->50. Değer yok/0/bozuk -> 0.5.

Kullanım:
  python -m app.seed_deadband            # uygula
  python -m app.seed_deadband --dry-run  # sadece özet
  python -m app.seed_deadband --reset    # tüm deadband'leri NULL yap
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tag import Tag, TagReading

DEFAULT = 0.5
GARBAGE = 1.0e9  # bunun üstü init edilmemiş/bozuk PLC okuması
# (üst sınır, deadband) — büyüklük tier'ları
TIERS = [(10, 0.1), (100, 0.5), (1000, 2.0), (100_000, 10.0)]
TOP_TIER = 50.0


def compute_deadband(data_type: str, latest_value: float | None) -> float | None:
    """Tek tag için deadband tier'ı. Ayrık tipler -> None (deadband yok)."""
    dt = (data_type or "").lower()
    # Float'ı önce kontrol et: "floating-point" içindeki "point" yanlışlıkla
    # "int" eşleşmesi vermesin.
    if "float" in dt or "real" in dt:
        if not latest_value:  # None veya 0
            return DEFAULT
        v = abs(latest_value)
        if v > GARBAGE:
            return DEFAULT
        for limit, db in TIERS:
            if v < limit:
                return db
        return TOP_TIER
    if "binary" in dt or "unsigned" in dt or "int" in dt:
        return None
    return None


async def _latest_values(db) -> dict[int, float | None]:
    """tag_id -> en son GOOD okumanın değeri (deadband için büyüklük referansı)."""
    rows = (
        await db.execute(
            select(TagReading.tag_id, TagReading.value)
            .where(TagReading.quality == 192)
            .order_by(TagReading.tag_id, TagReading.timestamp.desc())
        )
    ).all()
    out: dict[int, float | None] = {}
    for tag_id, value in rows:
        if tag_id not in out:  # ts desc sıralı -> ilk = en yeni
            out[tag_id] = value
    return out


async def main(*, dry_run: bool = False, reset: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        tags = (await db.execute(select(Tag))).scalars().all()
        latest = {} if reset else await _latest_values(db)

        changed = 0
        hist: dict[str, int] = {}
        for t in tags:
            new = None if reset else compute_deadband(t.data_type, latest.get(t.id))
            bucket = "NULL" if new is None else f"{new}"
            hist[bucket] = hist.get(bucket, 0) + 1
            if t.deadband != new:
                if not dry_run:
                    t.deadband = new
                changed += 1

        if not dry_run:
            await db.commit()

        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}Toplam {len(tags)} tag, {changed} güncellendi")
        print("Dağılım (deadband -> tag sayısı):")

        def _order(kv: tuple[str, int]) -> tuple[bool, float]:
            return (kv[0] == "NULL", float(kv[0]) if kv[0] != "NULL" else 0.0)

        for k, n in sorted(hist.items(), key=_order):
            print(f"  {k:>8}  {n}")


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(dry_run="--dry-run" in args, reset="--reset" in args))
