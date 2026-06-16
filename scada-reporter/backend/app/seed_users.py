"""Seed default users into database."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User

USERS = [
    {
        "username": "admin",
        "email": "admin@scada.local",
        "hashed_password": hash_password("admin123"),
        "full_name": "Sistem Yöneticisi",
        "role": "admin",
        "is_active": True,
    },
    {
        "username": "operator",
        "email": "operator@scada.local",
        "hashed_password": hash_password("operator123"),
        "full_name": "Operatör",
        "role": "operator",
        "is_active": True,
    },
]


async def main():
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User))
        existing_names = {u.username for u in existing.scalars().all()}
        count = 0
        for u in USERS:
            if u["username"] not in existing_names:
                db.add(User(**u))
                count += 1
                print(f"  + {u['username']} ({u['role']})")
        if count:
            await db.commit()
            print(f"{count} kullanıcı eklendi")
        else:
            print("Kullanıcılar zaten mevcut")


if __name__ == "__main__":
    asyncio.run(main())
