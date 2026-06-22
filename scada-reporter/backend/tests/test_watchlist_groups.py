import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist_group import WatchlistGroup, WatchlistGroupMember


@pytest.mark.asyncio
async def test_group_and_member_persist(db_session: AsyncSession):
    g = WatchlistGroup(user_id=1, name="Pompalar")
    db_session.add(g)
    await db_session.commit()
    db_session.add(WatchlistGroupMember(group_id=g.id, tag_id=42))
    await db_session.commit()
    rows = (await db_session.execute(select(WatchlistGroupMember))).scalars().all()
    assert len(rows) == 1
    assert rows[0].group_id == g.id and rows[0].tag_id == 42
