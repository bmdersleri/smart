"""Watchlist endpoint tests: per-user isolation, add/remove/list, readings."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TagReading


async def _register_and_login(client: AsyncClient, username: str) -> str:
    await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "pw123",
            "full_name": username,
        },
    )
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


async def _create_tag(db: AsyncSession, name: str, device: str = "DEV1") -> int:
    tag = Tag(node_id=f"ns=2;s={name}", name=name, device=device, long_term=True)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag.id


@pytest.mark.asyncio
async def test_watchlist_add_idempotent(client: AsyncClient, db_session: AsyncSession):
    """Pinning same tag twice must not create duplicate entries."""
    token = await _register_and_login(client, "wl_add_user")
    tag_id = await _create_tag(db_session, "WL_ADD_TAG")
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post(f"/api/dashboard/watchlist/{tag_id}", headers=headers)
    assert r1.status_code == 201

    # Second pin: endpoint may return 200 or 201 (idempotent), but list must not duplicate
    r2 = await client.post(f"/api/dashboard/watchlist/{tag_id}", headers=headers)
    assert r2.status_code in (200, 201)

    r_list = await client.get("/api/dashboard/watchlist", headers=headers)
    occurrences = sum(1 for item in r_list.json() if item["tag_id"] == tag_id)
    assert occurrences == 1, f"Expected 1 entry, got {occurrences}"


@pytest.mark.asyncio
async def test_watchlist_list_and_remove(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, "wl_list_user")
    tag_id = await _create_tag(db_session, "WL_LIST_TAG")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(f"/api/dashboard/watchlist/{tag_id}", headers=headers)
    r = await client.get("/api/dashboard/watchlist", headers=headers)
    assert r.status_code == 200
    ids = [item["tag_id"] for item in r.json()]
    assert tag_id in ids

    del_r = await client.delete(f"/api/dashboard/watchlist/{tag_id}", headers=headers)
    assert del_r.status_code == 204

    r2 = await client.get("/api/dashboard/watchlist", headers=headers)
    ids2 = [item["tag_id"] for item in r2.json()]
    assert tag_id not in ids2


@pytest.mark.asyncio
async def test_watchlist_user_isolation(client: AsyncClient, db_session: AsyncSession):
    token_a = await _register_and_login(client, "wl_iso_a")
    token_b = await _register_and_login(client, "wl_iso_b")
    tag_a = await _create_tag(db_session, "WL_ISO_TAG_A")
    tag_b = await _create_tag(db_session, "WL_ISO_TAG_B")

    await client.post(
        f"/api/dashboard/watchlist/{tag_a}", headers={"Authorization": f"Bearer {token_a}"}
    )
    await client.post(
        f"/api/dashboard/watchlist/{tag_b}", headers={"Authorization": f"Bearer {token_b}"}
    )

    r_a = await client.get(
        "/api/dashboard/watchlist", headers={"Authorization": f"Bearer {token_a}"}
    )
    ids_a = [item["tag_id"] for item in r_a.json()]
    assert tag_a in ids_a
    assert tag_b not in ids_a

    r_b = await client.get(
        "/api/dashboard/watchlist", headers={"Authorization": f"Bearer {token_b}"}
    )
    ids_b = [item["tag_id"] for item in r_b.json()]
    assert tag_b in ids_b
    assert tag_a not in ids_b


@pytest.mark.asyncio
async def test_watchlist_includes_reading(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, "wl_read_user")
    tag_id = await _create_tag(db_session, "WL_READ_TAG")
    headers = {"Authorization": f"Bearer {token}"}

    ts = datetime.now(UTC)
    db_session.add(TagReading(tag_id=tag_id, value=42.5, quality=192, timestamp=ts))
    await db_session.commit()

    await client.post(f"/api/dashboard/watchlist/{tag_id}", headers=headers)
    r = await client.get("/api/dashboard/watchlist", headers=headers)
    items = r.json()
    item = next((i for i in items if i["tag_id"] == tag_id), None)
    assert item is not None
    assert item["value"] == pytest.approx(42.5, abs=0.01)
    assert item["quality_ok"] is True


@pytest.mark.asyncio
async def test_watchlist_404_unknown_tag(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, "wl_404_user")
    r = await client.post(
        "/api/dashboard/watchlist/999999", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404
