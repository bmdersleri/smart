"""Tag group (hierarchy) tests: manual tree CRUD + assign + auto-derived tree."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User


async def _admin_token(client: AsyncClient, db: AsyncSession, username: str) -> str:
    db.add(
        User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


async def _mk_tag(db: AsyncSession, name: str, plc_name: str = "", device: str = "") -> int:
    tag = Tag(node_id=f"ns=2;s={name}", name=name, plc_name=plc_name, device=device, long_term=True)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag.id


@pytest.mark.asyncio
async def test_create_group(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "grp_create")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post("/api/groups/", json={"name": "Site A"}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Site A"
    assert body["parent_id"] is None
    assert isinstance(body["id"], int)


@pytest.mark.asyncio
async def test_create_group_requires_role(client: AsyncClient, db_session: AsyncSession):
    # viewer cannot create
    db_session.add(
        User(
            username="grp_viewer",
            email="v@t.com",
            hashed_password=hash_password("pw123"),
            role="viewer",
        )
    )
    await db_session.commit()
    tok = (
        await client.post("/api/auth/token", data={"username": "grp_viewer", "password": "pw123"})
    ).json()["access_token"]
    r = await client.post(
        "/api/groups/", json={"name": "Nope"}, headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_manual_tree_nesting_with_tags(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "grp_tree")
    h = {"Authorization": f"Bearer {tok}"}

    site = (await client.post("/api/groups/", json={"name": "Plant"}, headers=h)).json()
    unit = (
        await client.post(
            "/api/groups/", json={"name": "Aeration", "parent_id": site["id"]}, headers=h
        )
    ).json()

    tag_id = await _mk_tag(db_session, "Blower1")
    r = await client.post(f"/api/groups/{unit['id']}/assign", json={"tag_ids": [tag_id]}, headers=h)
    assert r.status_code == 200

    tree = (await client.get("/api/groups/tree", headers=h)).json()
    root = next(n for n in tree if n["id"] == site["id"])
    assert root["name"] == "Plant"
    child = next(c for c in root["children"] if c["id"] == unit["id"])
    assert tag_id in child["tag_ids"]


@pytest.mark.asyncio
async def test_unassign_clears_group(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "grp_unassign")
    h = {"Authorization": f"Bearer {tok}"}
    g = (await client.post("/api/groups/", json={"name": "G"}, headers=h)).json()
    tag_id = await _mk_tag(db_session, "UA_TAG")
    await client.post(f"/api/groups/{g['id']}/assign", json={"tag_ids": [tag_id]}, headers=h)

    r = await client.post("/api/groups/unassign", json={"tag_ids": [tag_id]}, headers=h)
    assert r.status_code == 200

    tree = (await client.get("/api/groups/tree", headers=h)).json()
    node = next(n for n in tree if n["id"] == g["id"])
    assert tag_id not in node["tag_ids"]


@pytest.mark.asyncio
async def test_delete_group_unassigns_tags(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "grp_del")
    h = {"Authorization": f"Bearer {tok}"}
    g = (await client.post("/api/groups/", json={"name": "Doomed"}, headers=h)).json()
    tag_id = await _mk_tag(db_session, "DEL_TAG")
    await client.post(f"/api/groups/{g['id']}/assign", json={"tag_ids": [tag_id]}, headers=h)

    r = await client.delete(f"/api/groups/{g['id']}", headers=h)
    assert r.status_code == 204

    # group gone
    flat = (await client.get("/api/groups/", headers=h)).json()
    assert all(n["id"] != g["id"] for n in flat)
    # tag survives, ungrouped
    tags = (await client.get("/api/tags/", headers=h)).json()
    survivor = next(t for t in tags if t["id"] == tag_id)
    assert survivor["group_id"] is None


@pytest.mark.asyncio
async def test_auto_tree_derives_from_plc_and_device(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "grp_auto")
    h = {"Authorization": f"Bearer {tok}"}
    await _mk_tag(db_session, "AT1", plc_name="PLC_A", device="Pump1")
    await _mk_tag(db_session, "AT2", plc_name="PLC_A", device="Pump2")
    await _mk_tag(db_session, "AT3", plc_name="PLC_B", device="Valve1")

    tree = (await client.get("/api/groups/tree?mode=auto", headers=h)).json()
    names = {n["name"] for n in tree}
    assert "PLC_A" in names
    assert "PLC_B" in names
    plc_a = next(n for n in tree if n["name"] == "PLC_A")
    devices = {c["name"] for c in plc_a["children"]}
    assert {"Pump1", "Pump2"} <= devices
