from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.tag import Tag, TagReading
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember
from app.services.grafana_sync import sync_groups

router = APIRouter(prefix="/dashboard/watchlist-groups", tags=["watchlist-groups"])


class GroupIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name boş olamaz")
        return v


async def _owned_group(db: AsyncSession, group_id: int, user_id: int) -> WatchlistGroup:
    g = await db.get(WatchlistGroup, group_id)
    if g is None or g.user_id != user_id:
        raise HTTPException(status_code=404, detail="Grup bulunamadı")
    return g


@router.get("/")
async def list_groups(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    groups = (
        (
            await db.execute(
                select(WatchlistGroup)
                .where(WatchlistGroup.user_id == user.id)
                .order_by(WatchlistGroup.sort_order, WatchlistGroup.name)
            )
        )
        .scalars()
        .all()
    )

    # members for these groups, with tag names
    members = (
        await db.execute(
            select(WatchlistGroupMember.group_id, WatchlistGroupMember.tag_id, Tag.name)
            .join(Tag, Tag.id == WatchlistGroupMember.tag_id)
            .join(WatchlistGroup, WatchlistGroup.id == WatchlistGroupMember.group_id)
            .where(WatchlistGroup.user_id == user.id)
        )
    ).all()
    by_group: dict[int, list[dict]] = {}
    grouped_tag_ids: set[int] = set()
    for gid, tid, tname in members:
        by_group.setdefault(gid, []).append({"tag_id": tid, "name": tname})
        grouped_tag_ids.add(tid)

    # watchlist tags not in any group → ungrouped
    wl = (
        await db.execute(
            select(Watchlist.tag_id, Tag.name)
            .join(Tag, Tag.id == Watchlist.tag_id)
            .where(Watchlist.user_id == user.id)
        )
    ).all()
    ungrouped = [{"tag_id": tid, "name": n} for tid, n in wl if tid not in grouped_tag_ids]

    return {
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "sort_order": g.sort_order,
                "tags": by_group.get(g.id, []),
                "tag_count": len(by_group.get(g.id, [])),
            }
            for g in groups
        ],
        "ungrouped": ungrouped,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    g = WatchlistGroup(user_id=user.id, name=body.name)
    db.add(g)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bu isimde grup zaten var") from None
    await db.refresh(g)
    return {"id": g.id, "name": g.name, "sort_order": g.sort_order, "tag_count": 0, "tags": []}


@router.patch("/{group_id}")
async def rename_group(
    group_id: int,
    body: GroupIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    g = await _owned_group(db, group_id, user.id)
    g.name = body.name.strip()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bu isimde grup zaten var") from None
    return {"id": g.id, "name": g.name}


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    g = await _owned_group(db, group_id, user.id)
    await db.execute(
        sa_delete(WatchlistGroupMember).where(WatchlistGroupMember.group_id == group_id)
    )
    await db.delete(g)
    await db.commit()


@router.post("/{group_id}/tags/{tag_id}", status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _owned_group(db, group_id, user.id)
    on_wl = await db.scalar(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.tag_id == tag_id)
    )
    if on_wl is None:
        raise HTTPException(status_code=400, detail="Tag watchlist'te değil")
    exists = await db.scalar(
        select(WatchlistGroupMember).where(
            WatchlistGroupMember.group_id == group_id, WatchlistGroupMember.tag_id == tag_id
        )
    )
    if exists:
        return {"status": "already_exists"}
    db.add(WatchlistGroupMember(group_id=group_id, tag_id=tag_id))
    await db.commit()
    return {"status": "added"}


@router.delete("/{group_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _owned_group(db, group_id, user.id)
    row = await db.scalar(
        select(WatchlistGroupMember).where(
            WatchlistGroupMember.group_id == group_id, WatchlistGroupMember.tag_id == tag_id
        )
    )
    if row:
        await db.delete(row)
        await db.commit()


@router.post("/sync-grafana")
async def sync_grafana(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    groups = (
        await db.execute(
            select(WatchlistGroup.id, WatchlistGroup.name).where(WatchlistGroup.user_id == user.id)
        )
    ).all()
    pairs = [(gid, name) for gid, name in groups]

    # Otomatik Y-eksen ayrımı için her grubun tag'lerinin son 6 saatteki tepe
    # büyüklüğü (|değer|). DB-portable (datetime eşiği Python'da, func.abs/max ile).
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=6)
    mag_rows = (
        await db.execute(
            select(
                WatchlistGroupMember.group_id,
                Tag.name,
                func.max(func.abs(TagReading.value)),
            )
            .join(Tag, Tag.id == WatchlistGroupMember.tag_id)
            .join(TagReading, TagReading.tag_id == WatchlistGroupMember.tag_id)
            .where(
                WatchlistGroupMember.group_id.in_([gid for gid, _ in pairs]),
                TagReading.timestamp >= since,
            )
            .group_by(WatchlistGroupMember.group_id, Tag.name)
        )
    ).all()
    magnitudes: dict[int, dict[str, float]] = {}
    for gid, tag_name, mag in mag_rows:
        if mag is not None:
            magnitudes.setdefault(gid, {})[tag_name] = float(mag)

    auth = (settings.GRAFANA_USER, settings.GRAFANA_PASSWORD)
    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL, auth=auth, timeout=10.0
        ) as http:
            result = await sync_groups(pairs, http=http, magnitudes=magnitudes)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    if result["written"] == 0 and result["errors"]:
        raise HTTPException(status_code=502, detail={"message": "Grafana senkron hatası", **result})
    return result
