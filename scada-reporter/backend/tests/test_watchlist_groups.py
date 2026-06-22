import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User
from app.models.watchlist import Watchlist
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
    body_post = r.json()
    assert "id" in body_post
    assert body_post["name"] == "Pompalar"
    assert body_post["sort_order"] is not None
    assert body_post["tag_count"] == 0
    assert body_post["tags"] == []
    gid = body_post["id"]
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


@pytest.mark.asyncio
async def test_create_group_blank_name_422(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gu3")
    r = await client.post("/api/dashboard/watchlist-groups/", json={"name": "   "}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ungrouped_lists_watchlist_tags_not_in_groups(
    client: AsyncClient, db_session: AsyncSession
):
    h = await _auth(client, db_session, "gu4")
    user = (await db_session.execute(select(User).where(User.username == "gu4"))).scalar_one()
    tag = Tag(name="TestTag", node_id="ns=2;s=TestTag", data_type="INT", unit="", description="")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(Watchlist(user_id=user.id, tag_id=tag.id))
    await db_session.commit()
    lst = await client.get("/api/dashboard/watchlist-groups/", headers=h)
    assert lst.status_code == 200
    body = lst.json()
    ungrouped_ids = [item["tag_id"] for item in body["ungrouped"]]
    assert tag.id in ungrouped_ids


@pytest.mark.asyncio
async def test_rename_and_delete_group(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gu5")
    gid = (
        await client.post("/api/dashboard/watchlist-groups/", json={"name": "A"}, headers=h)
    ).json()["id"]
    r = await client.patch(f"/api/dashboard/watchlist-groups/{gid}", json={"name": "B"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "B"
    d = await client.delete(f"/api/dashboard/watchlist-groups/{gid}", headers=h)
    assert d.status_code == 204
    lst = await client.get("/api/dashboard/watchlist-groups/", headers=h)
    assert all(g["id"] != gid for g in lst.json()["groups"])


@pytest.mark.asyncio
async def test_other_users_group_is_404(client: AsyncClient, db_session: AsyncSession):
    h1 = await _auth(client, db_session, "owner")
    gid = (
        await client.post("/api/dashboard/watchlist-groups/", json={"name": "Mine"}, headers=h1)
    ).json()["id"]
    h2 = await _auth(client, db_session, "intruder")
    r = await client.patch(
        f"/api/dashboard/watchlist-groups/{gid}", json={"name": "Hacked"}, headers=h2
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_and_remove_member(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gm")
    # create a tag + put on watchlist (membership precondition)
    db_session.add(Tag(node_id="N1,REAL0", name="T1"))
    await db_session.commit()
    tag = (await db_session.execute(select(Tag).where(Tag.name == "T1"))).scalar_one()
    # find the user id from token-created user
    uid = (await db_session.execute(select(User).where(User.username == "gm"))).scalar_one().id
    db_session.add(Watchlist(user_id=uid, tag_id=tag.id))
    await db_session.commit()
    gid = (
        await client.post("/api/dashboard/watchlist-groups/", json={"name": "G"}, headers=h)
    ).json()["id"]

    r = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert r.status_code == 201 and r.json()["status"] == "added"
    again = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert again.json()["status"] == "already_exists"

    body = (await client.get("/api/dashboard/watchlist-groups/", headers=h)).json()
    assert any(g["id"] == gid and g["tag_count"] == 1 for g in body["groups"])

    d = await client.delete(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert d.status_code == 204


@pytest.mark.asyncio
async def test_add_member_not_on_watchlist_400(client: AsyncClient, db_session: AsyncSession):
    h = await _auth(client, db_session, "gm2")
    db_session.add(Tag(node_id="N2,REAL0", name="T2"))
    await db_session.commit()
    tag = (await db_session.execute(select(Tag).where(Tag.name == "T2"))).scalar_one()
    gid = (
        await client.post("/api/dashboard/watchlist-groups/", json={"name": "G2"}, headers=h)
    ).json()["id"]
    r = await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_remove_watchlist_clears_group_membership(
    client: AsyncClient, db_session: AsyncSession
):
    h = await _auth(client, db_session, "gw")
    db_session.add(Tag(node_id="N3,REAL0", name="T3"))
    await db_session.commit()
    tag = (await db_session.execute(select(Tag).where(Tag.name == "T3"))).scalar_one()
    uid = (await db_session.execute(select(User).where(User.username == "gw"))).scalar_one().id
    db_session.add(Watchlist(user_id=uid, tag_id=tag.id))
    await db_session.commit()
    gid = (
        await client.post("/api/dashboard/watchlist-groups/", json={"name": "G"}, headers=h)
    ).json()["id"]
    await client.post(f"/api/dashboard/watchlist-groups/{gid}/tags/{tag.id}", headers=h)

    # remove from watchlist
    await client.delete(f"/api/dashboard/watchlist/{tag.id}", headers=h)

    body = (await client.get("/api/dashboard/watchlist-groups/", headers=h)).json()
    assert all(t["tag_id"] != tag.id for g in body["groups"] for t in g["tags"])
