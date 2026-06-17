import uuid

import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.core.security import hash_password, verify_password
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def operator(db_session):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        username=f"op_{suffix}",
        email=f"op_{suffix}@scada.local",
        hashed_password=hash_password("oldpass"),
        role="operator",
        permission_overrides={},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_me_returns_effective_permissions(client, operator):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert "tag:create" in perms
    assert "report_template:delete" not in perms  # operator default


@pytest.mark.asyncio
async def test_self_password_change_succeeds(client, operator, db_session):
    resp = await client.patch(
        "/api/auth/me",
        json={"current_password": "oldpass", "new_password": "newpass1"},
    )
    assert resp.status_code == 200
    await db_session.refresh(operator)
    assert verify_password("newpass1", operator.hashed_password)


@pytest.mark.asyncio
async def test_self_password_change_wrong_current(client, operator):
    resp = await client.patch(
        "/api/auth/me",
        json={"current_password": "WRONG", "new_password": "newpass1"},
    )
    assert resp.status_code == 400
