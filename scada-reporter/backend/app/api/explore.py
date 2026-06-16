from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import engine, get_db
from app.models.tag import Tag, TagReading
from app.models.user import User

router = APIRouter(prefix="/explore", tags=["explore"])


@router.get("/schema")
async def get_schema(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Veritabani semasini kesfet: tablolar, kolonlar, tipler, FK'lar."""
    # SQLite / PostgreSQL uyumlu sekilde
    db_type = engine.url.drivername
    tables = {}

    try:
        if "sqlite" in db_type:
            table_list = (
                await db.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                )
            ).all()
        else:
            table_list = (
                await db.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables"
                        " WHERE table_schema='public' ORDER BY table_name"
                    )
                )
            ).all()

        for (tname,) in table_list:
            if "sqlite" in db_type:
                col_rows = (await db.execute(text(f'PRAGMA table_info("{tname}")'))).all()
                columns = [
                    {
                        "name": r[1],
                        "type": r[2],
                        "nullable": not r[3],
                        "default": r[4],
                        "pk": bool(r[5]),
                    }
                    for r in col_rows
                ]
                fk_rows = (await db.execute(text(f'PRAGMA foreign_key_list("{tname}")'))).all()  # nosec B608
                foreign_keys = [
                    {"from": r[3], "to_table": r[2], "to_column": r[4]} for r in fk_rows
                ]
                row_count = (await db.execute(text(f'SELECT COUNT(*) FROM "{tname}"'))).scalar()  # nosec B608 — tname from SQLAlchemy reflection, not user input
            else:
                col_rows = (
                    await db.execute(
                        text(f"""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = '{tname}' AND table_schema = 'public'
                    ORDER BY ordinal_position
                """)  # nosec B608 — tname from SQLAlchemy reflection, not user input
                    )
                ).all()
                columns = [
                    {
                        "name": r[0],
                        "type": r[1],
                        "nullable": r[2] == "YES",
                        "default": r[3],
                    }
                    for r in col_rows
                ]
                foreign_keys = []
                row_count = (await db.execute(text(f'SELECT COUNT(*) FROM "{tname}"'))).scalar()  # nosec B608

            tables[tname] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            }

    except Exception as e:
        return {"error": str(e), "db_type": db_type}

    return {"db_type": db_type, "tables": tables}


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Veritabani ozet istatistikleri."""
    try:
        tag_count = await db.scalar(select(func.count(Tag.id)))
        active_tag_count = await db.scalar(select(func.count(Tag.id)).where(Tag.is_active))
        reading_count = await db.scalar(select(func.count(TagReading.timestamp)))
        user_count = await db.scalar(select(func.count(User.id)))

        # Cihaz bazinda tag dagilimi
        device_rows = (
            await db.execute(
                select(Tag.device, func.count(Tag.id)).group_by(Tag.device).order_by(Tag.device)
            )
        ).all()
        devices = {d: c for d, c in device_rows if d}

        # Kalite dagilimi
        quality_rows = (
            await db.execute(
                select(TagReading.quality, func.count(TagReading.timestamp)).group_by(
                    TagReading.quality
                )
            )
        ).all()
        quality_dist = {str(r[0]): r[1] for r in quality_rows}

        # Son okuma zamanlari
        last_overall = await db.scalar(select(func.max(TagReading.timestamp)))
        last_per_tag = (
            await db.execute(
                select(Tag.name, func.max(TagReading.timestamp))
                .join(TagReading, Tag.id == TagReading.tag_id, isouter=True)
                .group_by(Tag.id, Tag.name)
                .order_by(Tag.name)
                .limit(20)
            )
        ).all()

        return {
            "tags": {
                "total": tag_count,
                "active": active_tag_count,
                "inactive": (tag_count or 0) - (active_tag_count or 0),
            },
            "readings": {
                "total": reading_count,
                "last_overall": last_overall,
            },
            "users": user_count,
            "devices": devices,
            "quality_distribution": quality_dist,
            "recent_tag_activity": [{"tag": name, "last_reading": ts} for name, ts in last_per_tag],
        }
    except Exception as e:
        return {"error": str(e)}
