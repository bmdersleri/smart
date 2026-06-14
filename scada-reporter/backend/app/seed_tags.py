"""Seed S7 PLC tags into database."""
import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.tag import Tag

TAGS = [
    # DB171 - Pompa 1
    {"node_id": "DB171,REAL0", "name": "Pompa1_Debi", "unit": "m3/h",
     "device": "Pompa1", "channel": "Tesise_Giris"},
    {"node_id": "DB171,REAL12", "name": "Pompa1_Debi_2", "unit": "m3/h",
     "device": "Pompa1", "channel": "Tesise_Giris"},
    {"node_id": "DB171,REAL16", "name": "Pompa1_Debi_3", "unit": "m3/h",
     "device": "Pompa1", "channel": "Tesise_Giris"},
    {"node_id": "DB171,INT4", "name": "Pompa1_Status", "unit": "",
     "device": "Pompa1", "channel": "Tesise_Giris"},
    {"node_id": "DB171,INT8", "name": "Pompa1_Kontrol", "unit": "",
     "device": "Pompa1", "channel": "Tesise_Giris"},
    # DB172 - Pompa 2
    {"node_id": "DB172,REAL0", "name": "Pompa2_Debi", "unit": "m3/h",
     "device": "Pompa2", "channel": "Tesise_Giris"},
    {"node_id": "DB172,REAL12", "name": "Pompa2_Debi_2", "unit": "m3/h",
     "device": "Pompa2", "channel": "Tesise_Giris"},
    {"node_id": "DB172,REAL16", "name": "Pompa2_Debi_3", "unit": "m3/h",
     "device": "Pompa2", "channel": "Tesise_Giris"},
    {"node_id": "DB172,INT4", "name": "Pompa2_Status", "unit": "",
     "device": "Pompa2", "channel": "Tesise_Giris"},
    {"node_id": "DB172,INT8", "name": "Pompa2_Kontrol", "unit": "",
     "device": "Pompa2", "channel": "Tesise_Giris"},
    # DB177 - Havuz / Seviye
    {"node_id": "DB177,REAL0", "name": "Havuz_Seviye", "unit": "mm",
     "device": "Havuz", "channel": "Proses"},
    {"node_id": "DB177,REAL16", "name": "Havuz_Basinc", "unit": "bar",
     "device": "Havuz", "channel": "Proses"},
    # DB200 - Hat 1
    {"node_id": "DB200,REAL0", "name": "Hat1_Debi", "unit": "m3/h",
     "device": "Hat1", "channel": "Dagitim"},
    {"node_id": "DB200,REAL8", "name": "Hat1_Min", "unit": "m3/h",
     "device": "Hat1", "channel": "Dagitim"},
    {"node_id": "DB200,REAL16", "name": "Hat1_Max", "unit": "m3/h",
     "device": "Hat1", "channel": "Dagitim"},
    # DB201 - Hat 2
    {"node_id": "DB201,REAL0", "name": "Hat2_Debi", "unit": "m3/h",
     "device": "Hat2", "channel": "Dagitim"},
    {"node_id": "DB201,REAL8", "name": "Hat2_Min", "unit": "m3/h",
     "device": "Hat2", "channel": "Dagitim"},
    {"node_id": "DB201,REAL16", "name": "Hat2_Max", "unit": "m3/h",
     "device": "Hat2", "channel": "Dagitim"},
    # DB202 - Setpoint 1
    {"node_id": "DB202,REAL0", "name": "SP_Deger1", "unit": "",
     "device": "Setpoint", "channel": "Kontrol"},
    {"node_id": "DB202,REAL4", "name": "SP_Sure1", "unit": "sn",
     "device": "Setpoint", "channel": "Kontrol"},
    {"node_id": "DB202,REAL16", "name": "SP_Gercek1", "unit": "",
     "device": "Setpoint", "channel": "Kontrol"},
    # DB203 - Yogunluk / Seviye
    {"node_id": "DB203,REAL0", "name": "Yogunluk", "unit": "kg/m3",
     "device": "Kalite", "channel": "Analiz"},
    {"node_id": "DB203,REAL4", "name": "Kalite_Seviye", "unit": "mm",
     "device": "Kalite", "channel": "Analiz"},
    {"node_id": "DB203,REAL16", "name": "Kalite_Seviye_Max", "unit": "mm",
     "device": "Kalite", "channel": "Analiz"},
    # DB204 - Setpoint 2
    {"node_id": "DB204,REAL0", "name": "SP_Deger2", "unit": "",
     "device": "Setpoint", "channel": "Kontrol"},
    {"node_id": "DB204,REAL4", "name": "SP_Sure2", "unit": "sn",
     "device": "Setpoint", "channel": "Kontrol"},
    {"node_id": "DB204,REAL16", "name": "SP_Gercek2", "unit": "",
     "device": "Setpoint", "channel": "Kontrol"},
]


async def main():
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Tag))
        existing_ids = {t.node_id for t in existing.scalars().all()}
        count = 0
        for t in TAGS:
            if t["node_id"] not in existing_ids:
                db.add(Tag(**t))
                count += 1
        if count:
            await db.commit()
            print(f"{count} tag eklendi")
        else:
            print("Yeni tag yok, hepsi mevcut")


if __name__ == "__main__":
    asyncio.run(main())
