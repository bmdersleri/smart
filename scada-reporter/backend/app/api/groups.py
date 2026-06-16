"""Tag hiyerarşisi (gruplar) API.

İki ağaç sunar:
- **manuel**: `TagGroup` tablosundan kullanıcı-tanımlı Site→Ünite→Ekipman ağacı.
- **auto**: tag'lerin `plc_name` → `device` alanlarından türetilen ağaç (veri girişi yok).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_role
from app.core.database import get_db
from app.models.tag import Tag
from app.models.tag_group import TagGroup

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupCreate(BaseModel):
    name: str
    parent_id: int | None = None
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class GroupResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    sort_order: int

    model_config = {"from_attributes": True}


class TagIds(BaseModel):
    tag_ids: list[int]


@router.get("/", response_model=list[GroupResponse])
async def list_groups(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(TagGroup).order_by(TagGroup.sort_order, TagGroup.name))
    return result.scalars().all()


@router.get("/tree")
async def group_tree(
    mode: str = "manual",
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if mode == "auto":
        return await _auto_tree(db)
    return await _manual_tree(db)


async def _manual_tree(db: AsyncSession) -> list[dict]:
    groups = (
        (await db.execute(select(TagGroup).order_by(TagGroup.sort_order, TagGroup.name)))
        .scalars()
        .all()
    )
    tag_rows = (await db.execute(select(Tag.id, Tag.group_id, Tag.name))).all()

    tags_by_group: dict[int, list[int]] = {}
    for tag_id, group_id, _name in tag_rows:
        if group_id is not None:
            tags_by_group.setdefault(group_id, []).append(tag_id)

    nodes: dict[int, dict] = {
        g.id: {
            "id": g.id,
            "name": g.name,
            "parent_id": g.parent_id,
            "sort_order": g.sort_order,
            "tag_ids": tags_by_group.get(g.id, []),
            "children": [],
        }
        for g in groups
    }
    roots: list[dict] = []
    for g in groups:
        node = nodes[g.id]
        if g.parent_id is not None and g.parent_id in nodes:
            nodes[g.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


async def _auto_tree(db: AsyncSession) -> list[dict]:
    """plc_name → device ağacını tag verisinden türet."""
    rows = (await db.execute(select(Tag.id, Tag.plc_name, Tag.device, Tag.name))).all()
    plcs: dict[str, dict] = {}
    for tag_id, plc_name, device, _name in rows:
        plc_key = plc_name or device or "(gruplanmamış)"
        dev_key = device or "(diğer)"
        plc = plcs.setdefault(
            plc_key, {"id": None, "name": plc_key, "tag_ids": [], "children_map": {}}
        )
        dev = plc["children_map"].setdefault(dev_key, {"id": None, "name": dev_key, "tag_ids": []})
        dev["tag_ids"].append(tag_id)

    out: list[dict] = []
    for plc in sorted(plcs.values(), key=lambda p: p["name"]):
        children = [
            {"id": None, "name": d["name"], "tag_ids": d["tag_ids"], "children": []}
            for d in sorted(plc["children_map"].values(), key=lambda d: d["name"])
        ]
        out.append({"id": None, "name": plc["name"], "tag_ids": [], "children": children})
    return out


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    if data.parent_id is not None:
        parent = await db.get(TagGroup, data.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Üst grup bulunamadı")
    group = TagGroup(name=data.name, parent_id=data.parent_id, sort_order=data.sort_order)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    data: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    group = await db.get(TagGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    if data.parent_id == group_id:
        raise HTTPException(status_code=400, detail="Grup kendisinin üstü olamaz")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    group = await db.get(TagGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    # Tag'leri gruplanmamış yap, alt grupları silinenin üstüne taşı
    await db.execute(update(Tag).where(Tag.group_id == group_id).values(group_id=None))
    await db.execute(
        update(TagGroup).where(TagGroup.parent_id == group_id).values(parent_id=group.parent_id)
    )
    await db.delete(group)
    await db.commit()


@router.post("/{group_id}/assign")
async def assign_tags(
    group_id: int,
    data: TagIds,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    group = await db.get(TagGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    await db.execute(update(Tag).where(Tag.id.in_(data.tag_ids)).values(group_id=group_id))
    await db.commit()
    return {"assigned": len(data.tag_ids), "group_id": group_id}


@router.post("/unassign")
async def unassign_tags(
    data: TagIds,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "operator")),
):
    await db.execute(update(Tag).where(Tag.id.in_(data.tag_ids)).values(group_id=None))
    await db.commit()
    return {"unassigned": len(data.tag_ids)}
