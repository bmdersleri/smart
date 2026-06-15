from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.collector.s7_collector import plc_manager
from app.core.database import get_db
from app.models.plc_config import PlcConfig
from app.models.tag import Tag

router = APIRouter(prefix="/plc", tags=["plc"])


class PlcCreate(BaseModel):
    name: str
    ip: str = ""
    rack: int = 0
    slot: int = 1


class PlcUpdate(BaseModel):
    ip: str
    rack: int = 0
    slot: int = 1


@router.get("/")
async def list_plcs(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    # Tag-derived PLCs
    tag_rows = (
        await db.execute(
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
    ).all()

    tag_names = {r.plc_name for r in tag_rows}

    # Standalone PLCs (in plc_configs but no tags yet)
    config_rows = (
        (
            await db.execute(
                select(PlcConfig).where(PlcConfig.name.notin_(tag_names)).order_by(PlcConfig.name)
            )
        )
        .scalars()
        .all()
    )

    status = plc_manager.status()

    result = [
        {
            "name": r.plc_name,
            "ip": r.plc_ip or "",
            "rack": r.plc_rack,
            "slot": r.plc_slot,
            "tag_count": r.tag_count,
            "connected": status.get(r.plc_ip, False) if r.plc_ip else False,
        }
        for r in tag_rows
    ] + [
        {
            "name": c.name,
            "ip": c.ip,
            "rack": c.rack,
            "slot": c.slot,
            "tag_count": 0,
            "connected": status.get(c.ip, False) if c.ip else False,
        }
        for c in config_rows
    ]

    result.sort(key=lambda x: x["name"])
    return result


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_plc(
    data: PlcCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="PLC adı boş olamaz")

    # Check duplicate in tags
    existing_tag = await db.scalar(select(Tag.plc_name).where(Tag.plc_name == name).limit(1))
    if existing_tag:
        raise HTTPException(status_code=409, detail="Bu isimde tag'ler mevcut")

    # Check duplicate in plc_configs
    existing_cfg = await db.scalar(select(PlcConfig.id).where(PlcConfig.name == name).limit(1))
    if existing_cfg:
        raise HTTPException(status_code=409, detail="Bu PLC zaten kayıtlı")

    cfg = PlcConfig(name=name, ip=data.ip, rack=data.rack, slot=data.slot)
    db.add(cfg)
    await db.commit()
    return {
        "name": name,
        "ip": data.ip,
        "rack": data.rack,
        "slot": data.slot,
        "tag_count": 0,
        "connected": False,
    }


@router.patch("/{name}")
async def update_plc(
    name: str,
    data: PlcUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Update tags
    await db.execute(
        update(Tag)
        .where(Tag.plc_name == name)
        .values(plc_ip=data.ip, plc_rack=data.rack, plc_slot=data.slot)
    )
    # Upsert plc_config
    cfg = await db.scalar(select(PlcConfig).where(PlcConfig.name == name))
    if cfg:
        cfg.ip = data.ip
        cfg.rack = data.rack
        cfg.slot = data.slot
    await db.commit()
    return {"updated": True, "plc_name": name}


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plc(
    name: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Delete all tags belonging to this PLC
    await db.execute(delete(Tag).where(Tag.plc_name == name))
    # Delete plc_config if exists
    await db.execute(delete(PlcConfig).where(PlcConfig.name == name))
    await db.commit()
