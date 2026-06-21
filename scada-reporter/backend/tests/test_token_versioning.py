"""Token versioning tests (Task 5 — Phase 3).

Verifies that:
- A freshly issued token authenticates normally.
- After an admin resets a user's password the OLD token becomes 401;
  a new token (re-login) is 200.
- After an admin deactivates a user the old token becomes 401 (both via
  is_active AND ver).
- After reactivation the OLD token is STILL 401 (proves ver-based
  invalidation independent of is_active).
- A token WITHOUT a 'ver' claim (legacy / manually crafted) for a user
  whose token_version is still 0 is accepted (backward-compat).
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique(prefix: str = "tv") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_user(db_session, *, username, password="pass1234", role="operator") -> User:
    u = User(
        username=username,
        email=f"{username}@scada.local",
        hashed_password=hash_password(password),
        role=role,
        permission_overrides={},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """Login via /api/auth/token (form-data) and return the access token."""
    resp = await client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


async def _admin_reset_password(
    client: AsyncClient, admin_token: str, user_id: int, new_password: str
) -> None:
    resp = await client.post(
        f"/api/users/{user_id}/password",
        json={"password": new_password},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Password reset failed: {resp.text}"


async def _admin_patch(client: AsyncClient, admin_token: str, user_id: int, payload: dict) -> None:
    resp = await client.patch(
        f"/api/users/{user_id}",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Patch failed: {resp.text}"


async def _me(client: AsyncClient, token: str) -> int:
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return resp.status_code


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def full_client(db_session):
    """AsyncClient with real DB dependency (not override) for end-to-end flows."""
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_and_token(db_session, full_client):
    """Create an admin user and return (user, token)."""
    name = _unique("adm")
    admin = await _create_user(db_session, username=name, password="adminpass", role="admin")
    token = await _login(full_client, name, "adminpass")
    return admin, token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_token_authenticates(db_session, full_client):
    """A freshly issued token must return 200 on /auth/me."""
    name = _unique()
    await _create_user(db_session, username=name, password="pass1234")
    token = await _login(full_client, name, "pass1234")
    assert await _me(full_client, token) == 200


@pytest.mark.asyncio
async def test_old_token_invalid_after_password_reset(db_session, full_client, admin_and_token):
    """After admin resets password, old token → 401; new token → 200."""
    admin, admin_token = admin_and_token
    name = _unique()
    user = await _create_user(db_session, username=name, password="original")
    old_token = await _login(full_client, name, "original")

    # Verify old token works before reset
    assert await _me(full_client, old_token) == 200

    # Admin resets password
    await _admin_reset_password(full_client, admin_token, user.id, "newpassword")

    # Old token must now be 401
    assert await _me(full_client, old_token) == 401

    # New token (re-login with new password) must work
    new_token = await _login(full_client, name, "newpassword")
    assert await _me(full_client, new_token) == 200


@pytest.mark.asyncio
async def test_old_token_invalid_after_deactivation(db_session, full_client, admin_and_token):
    """After admin deactivates user, old token → 401."""
    admin, admin_token = admin_and_token
    name = _unique()
    user = await _create_user(db_session, username=name, password="pass1234")
    old_token = await _login(full_client, name, "pass1234")

    assert await _me(full_client, old_token) == 200

    # Admin deactivates user
    await _admin_patch(full_client, admin_token, user.id, {"is_active": False})

    # Old token must now be 401 (both is_active=False and ver mismatch)
    assert await _me(full_client, old_token) == 401


@pytest.mark.asyncio
async def test_old_token_still_invalid_after_reactivation(db_session, full_client, admin_and_token):
    """After deactivate then reactivate, the original old token is STILL 401.

    This proves token_version-based invalidation works independently of
    the is_active flag: reactivation does not restore old tokens.
    """
    admin, admin_token = admin_and_token
    name = _unique()
    user = await _create_user(db_session, username=name, password="pass1234")
    old_token = await _login(full_client, name, "pass1234")

    # Deactivate → old token dies
    await _admin_patch(full_client, admin_token, user.id, {"is_active": False})
    assert await _me(full_client, old_token) == 401

    # Reactivate
    await _admin_patch(full_client, admin_token, user.id, {"is_active": True})

    # Old token is STILL 401 (token_version was bumped on deactivate, not reset)
    assert await _me(full_client, old_token) == 401

    # Fresh login after reactivation works
    new_token = await _login(full_client, name, "pass1234")
    assert await _me(full_client, new_token) == 200


@pytest.mark.asyncio
async def test_legacy_token_without_ver_claim_is_accepted(db_session, full_client):
    """A token WITHOUT a 'ver' claim (legacy) for a user with token_version=0 → 200.

    Backward compatibility: payload.get('ver', 0) == 0 == user.token_version.
    """
    name = _unique()
    user = await _create_user(db_session, username=name, password="pass1234")
    # Manually craft a token WITHOUT the 'ver' claim (simulates pre-Task-5 tokens)
    legacy_token = create_access_token({"sub": user.username, "role": user.role})
    assert await _me(full_client, legacy_token) == 200


@pytest.mark.asyncio
async def test_token_version_not_bumped_on_other_patches(db_session, full_client, admin_and_token):
    """Patching email/full_name/role alone must NOT invalidate existing tokens."""
    admin, admin_token = admin_and_token
    name = _unique()
    user = await _create_user(db_session, username=name, password="pass1234")
    token = await _login(full_client, name, "pass1234")

    # Patch unrelated fields
    await _admin_patch(full_client, admin_token, user.id, {"full_name": "New Name"})

    # Token must still work
    assert await _me(full_client, token) == 200
