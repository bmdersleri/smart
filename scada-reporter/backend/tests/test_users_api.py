from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _admin():
    return SimpleNamespace(
        id=1, username="admin", role="admin", permission_overrides={}, is_active=True
    )


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    yield
    await db_session.execute(delete(User))
    await db_session.commit()


@pytest_asyncio.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = _admin
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seed_admin(db_session):
    a = User(
        username="root",
        email="root@scada.local",
        hashed_password=hash_password("x"),
        role="admin",
        permission_overrides={},
        is_active=True,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


@pytest.mark.asyncio
async def test_create_and_list_user(client, as_admin):
    resp = await client.post(
        "/api/users/",
        json={
            "username": "bob",
            "email": "bob@scada.local",
            "password": "secret1",
            "full_name": "Bob",
            "role": "operator",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "bob"
    assert "report_template:delete" not in body["permissions"]

    lst = await client.get("/api/users/")
    assert lst.status_code == 200
    assert any(u["username"] == "bob" for u in lst.json())


@pytest.mark.asyncio
async def test_create_duplicate_username_409(client, as_admin):
    payload = {"username": "dup", "email": "d1@scada.local", "password": "secret1"}
    assert (await client.post("/api/users/", json=payload)).status_code == 201
    payload2 = {"username": "dup", "email": "d2@scada.local", "password": "secret1"}
    assert (await client.post("/api/users/", json=payload2)).status_code == 409


@pytest.mark.asyncio
async def test_patch_role_and_overrides(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "carol", "email": "c@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "operator", "permission_overrides": {"report_template:delete": True}},
    )
    assert resp.status_code == 200
    assert "report_template:delete" in resp.json()["permissions"]


@pytest.mark.asyncio
async def test_reset_password(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "dave", "email": "dv@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.post(f"/api/users/{created['id']}/password", json={"password": "newsecret"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_user(client, as_admin):
    created = (
        await client.post(
            "/api/users/",
            json={"username": "erin", "email": "e@scada.local", "password": "secret1"},
        )
    ).json()
    resp = await client.delete(f"/api/users/{created['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_last_active_admin(client, as_admin, seed_admin):
    # seed_admin ("root") is the only DB admin. _admin override (id=1) is not in DB.
    resp = await client.delete(f"/api/users/{seed_admin.id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_demote_last_active_admin(client, as_admin, seed_admin):
    resp = await client.patch(f"/api/users/{seed_admin.id}", json={"role": "operator"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, username="op", role="operator", permission_overrides={}, is_active=True
    )
    try:
        resp = await client.get("/api/users/")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
