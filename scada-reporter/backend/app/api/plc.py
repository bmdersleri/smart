from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.collector.s7_collector import plc_manager
from app.core.database import get_db
from app.models.tag import Tag

router = APIRouter(prefix="/plc", tags=["plc"])


class PlcUpdate(BaseModel):
    ip: str
    rack: int = 0
    slot: int = 1


@router.get("/")
async def list_plcs(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(
            Tag.plc_name,
            Tag.plc_ip,
            Tag.plc_rack,
            Tag.plc_slot,
            func.count(Tag.id).label("tag_count"),
        )
        .where(Tag.plc_name != "", Tag.is_active, Tag.long_term)
        .group_by(Tag.plc_name, Tag.plc_ip, Tag.plc_rack, Tag.plc_slot)
        .order_by(Tag.plc_name)
    )
    status = plc_manager.status()  # {ip: bool}
    return [
        {
            "name": row.plc_name,
            "ip": row.plc_ip or "",
            "rack": row.plc_rack,
            "slot": row.plc_slot,
            "tag_count": row.tag_count,
            "connected": status.get(row.plc_ip, False) if row.plc_ip else False,
        }
        for row in result
    ]


@router.patch("/{name}")
async def update_plc(
    name: str,
    data: PlcUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(
        update(Tag)
        .where(Tag.plc_name == name)
        .values(plc_ip=data.ip, plc_rack=data.rack, plc_slot=data.slot)
    )
    await db.commit()
    return {"updated": True, "plc_name": name}
