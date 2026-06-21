"""Tests for RBAC role constraint (Task 2 — Phase 3).

Covers:
- Pydantic schema rejects invalid roles → HTTP 422
- Valid roles (admin/operator/viewer) accepted by API
- DB-level CHECK constraint via create_all (in-memory SQLite)
- Migration upgrade/downgrade covered by test suite (alembic tested separately)
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.user import User

# ---------------------------------------------------------------------------
# Local fixtures (scoped to this module)
# ---------------------------------------------------------------------------


def _admin():
    return SimpleNamespace(
        id=9999, username="admin", role="admin", permission_overrides={}, is_active=True
    )


@pytest_asyncio.fixture(autouse=True)
async def _clean_users(db_session):
    """Clean users table before each test in this module."""
    yield
    await db_session.execute(delete(User))
    await db_session.commit()


@pytest_asyncio.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = _admin
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# API: schema validation — invalid role → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_invalid_role_422(client, as_admin):
    """POST /api/users/ with an invalid role must return 422."""
    resp = await client.post(
        "/api/users/",
        json={
            "username": "badrol",
            "email": "badrol@scada.local",
            "password": "secret1",
            "role": "superuser",
        },
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_patch_user_invalid_role_422(client, as_admin):
    """PATCH /api/users/{id} with an invalid role must return 422."""
    created = (
        await client.post(
            "/api/users/",
            json={
                "username": "patchme",
                "email": "patchme@scada.local",
                "password": "secret1",
                "role": "operator",
            },
        )
    ).json()
    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "god"},
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# API: valid roles accepted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
async def test_create_user_valid_role(client, as_admin, role):
    """Each valid role must be accepted by POST /api/users/."""
    resp = await client.post(
        "/api/users/",
        json={
            "username": f"user_{role}",
            "email": f"{role}@scada.local",
            "password": "secret1",
            "role": role,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == role


# ---------------------------------------------------------------------------
# DB-level CHECK constraint (via create_all in-memory SQLite)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_check_constraint_rejects_bogus_role(db_engine):
    """Inserting a User with role='bogus' must raise IntegrityError."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        bad_user = User(
            username="bogusrole_user",
            email="bogusrole@scada.local",
            hashed_password=hash_password("x"),
            role="bogus",
            permission_overrides={},
        )
        session.add(bad_user)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_db_check_constraint_accepts_valid_role(db_engine):
    """Inserting a User with role='viewer' must succeed."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        good_user = User(
            username="vieweruser_ck",
            email="viewerck@scada.local",
            hashed_password=hash_password("x"),
            role="viewer",
            permission_overrides={},
        )
        session.add(good_user)
        await session.flush()
        assert good_user.id is not None
        await session.rollback()  # don't persist — let autouse _isolate_db handle cleanup
