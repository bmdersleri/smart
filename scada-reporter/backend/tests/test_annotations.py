"""Trend annotation tests: shared DB-backed notes, range/tag filter, delete perms."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User


async def _login(
    client: AsyncClient, db: AsyncSession, username: str, role: str = "operator"
) -> str:
    user = User(
        username=username,
        email=f"{username}@t.com",
        hashed_password=hash_password("pw123"),
        role=role,
    )
    db.add(user)
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


async def _mk_tag(db: AsyncSession, name: str) -> int:
    tag = Tag(node_id=f"ns=2;s={name}", name=name, long_term=True)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag.id


@pytest.mark.asyncio
async def test_create_annotation_records_author(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "ann_create")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _mk_tag(db_session, "ANN_TAG")
    ts = datetime.now(UTC).isoformat()
    r = await client.post(
        "/api/annotations/", json={"tag_id": tag_id, "ts": ts, "text": "valf açıldı"}, headers=h
    )
    assert r.status_code == 201
    body = r.json()
    assert body["text"] == "valf açıldı"
    assert body["username"] == "ann_create"
    assert body["tag_id"] == tag_id


@pytest.mark.asyncio
async def test_list_filters_by_tag(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "ann_tagfilter")
    h = {"Authorization": f"Bearer {tok}"}
    t1 = await _mk_tag(db_session, "ANN_T1")
    t2 = await _mk_tag(db_session, "ANN_T2")
    ts = datetime.now(UTC).isoformat()
    await client.post("/api/annotations/", json={"tag_id": t1, "ts": ts, "text": "a"}, headers=h)
    await client.post("/api/annotations/", json={"tag_id": t2, "ts": ts, "text": "b"}, headers=h)

    r = await client.get("/api/annotations/", params={"tag_ids": [t1]}, headers=h)
    assert r.status_code == 200
    texts = [a["text"] for a in r.json()]
    assert "a" in texts
    assert "b" not in texts


@pytest.mark.asyncio
async def test_list_filters_by_range(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "ann_range")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _mk_tag(db_session, "ANN_RANGE")
    now = datetime.now(UTC)
    old = (now - timedelta(days=10)).isoformat()
    recent = now.isoformat()
    await client.post(
        "/api/annotations/", json={"tag_id": tag_id, "ts": old, "text": "old"}, headers=h
    )
    await client.post(
        "/api/annotations/", json={"tag_id": tag_id, "ts": recent, "text": "recent"}, headers=h
    )

    start = (now - timedelta(days=1)).isoformat()
    r = await client.get("/api/annotations/", params={"start": start}, headers=h)
    texts = [a["text"] for a in r.json()]
    assert "recent" in texts
    assert "old" not in texts


@pytest.mark.asyncio
async def test_owner_can_delete(client: AsyncClient, db_session: AsyncSession):
    tok = await _login(client, db_session, "ann_owner")
    h = {"Authorization": f"Bearer {tok}"}
    tag_id = await _mk_tag(db_session, "ANN_OWN")
    ts = datetime.now(UTC).isoformat()
    aid = (
        await client.post(
            "/api/annotations/", json={"tag_id": tag_id, "ts": ts, "text": "x"}, headers=h
        )
    ).json()["id"]
    r = await client.delete(f"/api/annotations/{aid}", headers=h)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_non_owner_cannot_delete(client: AsyncClient, db_session: AsyncSession):
    tok_a = await _login(client, db_session, "ann_a")
    tok_b = await _login(client, db_session, "ann_b")
    tag_id = await _mk_tag(db_session, "ANN_PERM")
    ts = datetime.now(UTC).isoformat()
    aid = (
        await client.post(
            "/api/annotations/",
            json={"tag_id": tag_id, "ts": ts, "text": "x"},
            headers={"Authorization": f"Bearer {tok_a}"},
        )
    ).json()["id"]
    r = await client.delete(f"/api/annotations/{aid}", headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_others(client: AsyncClient, db_session: AsyncSession):
    tok_user = await _login(client, db_session, "ann_u")
    tok_admin = await _login(client, db_session, "ann_admin", role="admin")
    tag_id = await _mk_tag(db_session, "ANN_ADMIN")
    ts = datetime.now(UTC).isoformat()
    aid = (
        await client.post(
            "/api/annotations/",
            json={"tag_id": tag_id, "ts": ts, "text": "x"},
            headers={"Authorization": f"Bearer {tok_user}"},
        )
    ).json()["id"]
    r = await client.delete(
        f"/api/annotations/{aid}", headers={"Authorization": f"Bearer {tok_admin}"}
    )
    assert r.status_code == 204
