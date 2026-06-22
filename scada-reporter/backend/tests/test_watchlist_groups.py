import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
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


async def _auth(client, db_session, uname="gu"):
    db_session.add(
        User(
            username=uname,
            email=f"{uname}@t.com",
            hashed_password=hash_password("test123"),
            role="admin",
        )
    )
    await db_session.commit()
    tok = await client.post("/api/auth/token", data={"username": uname, "password": "test123"})
    return {"Authorization": f"Bearer {tok.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_and_list_group(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session)
    r = await client.post("/api/dashboard/watchlist-groups/", json={"name": "Pompalar"}, headers=h)
    assert r.status_code == 201
    gid = r.json()["id"]
    lst = await client.get("/api/dashboard/watchlist-groups/", headers=h)
    assert lst.status_code == 200
    body = lst.json()
    assert any(
        g["id"] == gid and g["name"] == "Pompalar" and g["tag_count"] == 0 for g in body["groups"]
    )
    assert "ungrouped" in body


@pytest.mark.asyncio
async def test_create_duplicate_name_conflicts(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gu2")
    await client.post("/api/dashboard/watchlist-groups/", json={"name": "X"}, headers=h)
    r = await client.post("/api/dashboard/watchlist-groups/", json={"name": "X"}, headers=h)
    assert r.status_code == 409
