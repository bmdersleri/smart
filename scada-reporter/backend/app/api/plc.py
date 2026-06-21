from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_perm
from app.collector.s7_collector import plc_manager
from app.core.database import get_db
from app.models.plc_config import PlcConfig
from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
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
    _=Depends(require_perm("plc:manage")),
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
    _=Depends(require_perm("plc:manage")),
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
    _=Depends(require_perm("plc:manage")),
):
    # Delete all tags belonging to this PLC
    await db.execute(delete(Tag).where(Tag.plc_name == name))
    # Delete plc_config if exists
    await db.execute(delete(PlcConfig).where(PlcConfig.name == name))
    await db.commit()


@router.get("/health")
async def plc_health(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (await db.execute(select(PlcHealth).order_by(PlcHealth.plc_name))).scalars().all()
    return [
        {
            "plc_ip": r.plc_ip,
            "plc_name": r.plc_name,
            "rack": r.rack,
            "slot": r.slot,
            "connected": r.connected,
            "last_success_at": r.last_success_at,
            "consecutive_fail": r.consecutive_fail,
            "last_error": r.last_error,
            "good_last_cycle": r.good_last_cycle,
            "bad_last_cycle": r.bad_last_cycle,
            "reconnects_last_min": r.reconnects_last_min,
            "open_incident_count": r.open_incident_count,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def _incident_dict(r: PlcIncident) -> dict:
    return {
        "id": r.id,
        "plc_ip": r.plc_ip,
        "plc_name": r.plc_name,
        "kind": r.kind,
        "severity": r.severity,
        "message": r.message,
        "detail": r.detail,
        "opened_at": r.opened_at,
        "resolved_at": r.resolved_at,
        "acknowledged_by": r.acknowledged_by,
        "acknowledged_at": r.acknowledged_at,
    }


@router.get("/incidents/summary")
async def incidents_summary(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (
        (await db.execute(select(PlcIncident).where(PlcIncident.resolved_at.is_(None))))
        .scalars()
        .all()
    )
    critical = sum(1 for r in rows if r.severity == "critical")
    warning = sum(1 for r in rows if r.severity == "warning")
    return {"open_total": len(rows), "critical": critical, "warning": warning}


@router.get("/incidents")
async def list_incidents(
    open: bool | None = None,
    plc: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(PlcIncident).order_by(PlcIncident.opened_at.desc())
    if open is True:
        stmt = stmt.where(PlcIncident.resolved_at.is_(None))
    elif open is False:
        stmt = stmt.where(PlcIncident.resolved_at.is_not(None))
    if plc:
        stmt = stmt.where(PlcIncident.plc_ip == plc)
    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [_incident_dict(r) for r in rows]


@router.post("/incidents/{incident_id}/ack")
async def ack_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("plc:manage")),
):
    inc = await db.get(PlcIncident, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident bulunamadı")
    inc.acknowledged_by = user.username
    inc.acknowledged_at = datetime.now(UTC)
    await db.commit()
    return {"acknowledged": True, "id": incident_id}
