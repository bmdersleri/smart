"""Tests for the admin audit-log feature (Task 3 / Phase 3).

Coverage:
  - Each admin user-mutation writes the correct audit row(s).
  - GET /api/audit is admin-only; returns rows newest-first; pagination works.
  - Passwords are never stored in audit detail.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_ns(user_id: int = 9999, username: str = "admin"):
    return SimpleNamespace(
        id=user_id, username=username, role="admin", permission_overrides={}, is_active=True
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    """Clean users and audit_logs before each test."""
    yield
    await db_session.execute(delete(AuditLog))
    await db_session.execute(delete(User))
    await db_session.commit()


@pytest_asyncio.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: _admin_ns()
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seed_admin(db_session):
    a = User(
        username="root",
        email="root@audit.local",
        hashed_password=hash_password("x"),
        role="admin",
        permission_overrides={},
        is_active=True,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Helper: read all audit rows from db
# ---------------------------------------------------------------------------


async def _all_audit(db_session):
    result = await db_session.execute(select(AuditLog).order_by(AuditLog.id))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Mutation audit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_writes_audit(client, db_session, as_admin):
    """POST /users/ creates exactly 1 audit row with action=user.create."""
    resp = await client.post(
        "/api/users/",
        json={
            "username": "alice",
            "email": "alice@audit.local",
            "password": "secret1",
            "role": "operator",
        },
    )
    assert resp.status_code == 201, resp.text

    rows = await _all_audit(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "user.create"
    assert row.target_type == "user"
    assert row.actor_username == "admin"
    assert row.target_id == str(resp.json()["id"])
    assert row.detail_dict.get("username") == "alice"
    assert row.detail_dict.get("role") == "operator"


@pytest.mark.asyncio
async def test_patch_user_without_role_change_writes_one_update_row(client, db_session, as_admin):
    """PATCH without role change → exactly 1 user.update row."""
    created = (
        await client.post(
            "/api/users/",
            json={
                "username": "bob",
                "email": "bob@audit.local",
                "password": "secret1",
                "role": "operator",
            },
        )
    ).json()
    # Clear audit rows from create
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"full_name": "Bob Smith"},
    )
    assert resp.status_code == 200

    rows = await _all_audit(db_session)
    actions = [r.action for r in rows]
    assert actions == ["user.update"]
    assert rows[0].actor_username == "admin"


@pytest.mark.asyncio
async def test_patch_user_with_role_change_writes_update_and_role_change(
    client, db_session, as_admin
):
    """PATCH with role change → user.update + user.role_change rows."""
    created = (
        await client.post(
            "/api/users/",
            json={
                "username": "carol",
                "email": "carol@audit.local",
                "password": "secret1",
                "role": "operator",
            },
        )
    ).json()
    # Clear audit rows from create
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "viewer"},
    )
    assert resp.status_code == 200

    rows = await _all_audit(db_session)
    actions = [r.action for r in rows]
    assert "user.update" in actions
    assert "user.role_change" in actions

    role_row = next(r for r in rows if r.action == "user.role_change")
    assert role_row.detail_dict.get("from") == "operator"
    assert role_row.detail_dict.get("to") == "viewer"


@pytest.mark.asyncio
async def test_reset_password_writes_audit_no_password(client, db_session, as_admin):
    """POST /users/{id}/password → user.password_reset row; no password in detail."""
    created = (
        await client.post(
            "/api/users/",
            json={"username": "dave", "email": "dave@audit.local", "password": "secret1"},
        )
    ).json()
    # Clear audit rows from create
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.post(
        f"/api/users/{created['id']}/password",
        json={"password": "newpass1"},
    )
    assert resp.status_code == 200

    rows = await _all_audit(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "user.password_reset"
    assert row.actor_username == "admin"
    # Password must NEVER appear in detail
    detail_str = row.detail or ""
    assert "newpass1" not in detail_str
    assert "secret1" not in detail_str
    assert "password" not in detail_str.lower()


@pytest.mark.asyncio
async def test_register_writes_audit(client, db_session, as_admin):
    """POST /auth/register creates exactly 1 audit row with action=user.create."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": "newbie",
            "email": "newbie@audit.local",
            "password": "secret42",
            "full_name": "New User",
            "role": "operator",
        },
    )
    assert resp.status_code == 201, resp.text

    created_id = resp.json()["id"]

    rows = await _all_audit(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "user.create"
    assert row.target_type == "user"
    assert row.actor_username == "admin"
    assert row.target_id == str(created_id)
    assert row.detail_dict.get("username") == "newbie"
    # Password must never appear in the audit detail
    detail_str = row.detail or ""
    assert "secret42" not in detail_str
    assert "password" not in detail_str.lower()


@pytest.mark.asyncio
async def test_delete_user_writes_audit(client, db_session, as_admin, seed_admin):
    """DELETE /users/{id} → exactly 1 user.delete row."""
    created = (
        await client.post(
            "/api/users/",
            json={
                "username": "erin",
                "email": "erin@audit.local",
                "password": "secret1",
                "role": "operator",
            },
        )
    ).json()
    # Clear audit rows from create
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.delete(f"/api/users/{created['id']}")
    assert resp.status_code == 204

    rows = await _all_audit(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "user.delete"
    assert row.detail_dict.get("username") == "erin"
    assert row.actor_username == "admin"


# ---------------------------------------------------------------------------
# GET /api/audit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_endpoint_admin_gets_rows(client, as_admin):
    """Admin can retrieve audit log rows."""
    # Create a user to generate some audit rows
    await client.post(
        "/api/users/",
        json={"username": "frank", "email": "frank@audit.local", "password": "secret1"},
    )
    resp = await client.get("/api/audit/")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
    row = rows[0]
    assert "action" in row
    assert "actor_username" in row
    assert "timestamp" in row


@pytest.mark.asyncio
async def test_audit_endpoint_non_admin_403(client):
    """Non-admin gets 403 on GET /api/audit."""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, username="op", role="operator", permission_overrides={}, is_active=True
    )
    try:
        resp = await client.get("/api/audit/")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_audit_newest_first(client, db_session, as_admin):
    """Audit rows are returned newest-first."""
    # Create two users sequentially to get two audit rows
    await client.post(
        "/api/users/",
        json={"username": "first", "email": "first@audit.local", "password": "secret1"},
    )
    await client.post(
        "/api/users/",
        json={"username": "second", "email": "second@audit.local", "password": "secret1"},
    )

    resp = await client.get("/api/audit/")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 2
    # "second" should come before "first" (newest-first)
    usernames = [r["detail"]["username"] for r in rows if r["detail"] and "username" in r["detail"]]
    assert usernames[0] == "second"
    assert usernames[1] == "first"


@pytest.mark.asyncio
async def test_audit_pagination(client, as_admin):
    """limit/offset pagination works on GET /api/audit."""
    # Create 3 users → 3 audit rows
    for i in range(3):
        await client.post(
            "/api/users/",
            json={"username": f"pg{i}", "email": f"pg{i}@audit.local", "password": "secret1"},
        )

    resp_all = await client.get("/api/audit/?limit=3&offset=0")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 3

    resp_page = await client.get("/api/audit/?limit=2&offset=0")
    assert len(resp_page.json()) == 2

    resp_offset = await client.get("/api/audit/?limit=2&offset=2")
    assert len(resp_offset.json()) == 1

    # limit > max (200) should be rejected
    resp_over = await client.get("/api/audit/?limit=201")
    assert resp_over.status_code == 422


@pytest.mark.asyncio
async def test_password_never_in_audit_detail(client, db_session, as_admin):
    """Verify passwords do not appear in any audit row detail field."""
    await client.post(
        "/api/users/",
        json={"username": "secure", "email": "secure@audit.local", "password": "mySecretPass"},
    )
    await client.post("/api/users/secure/password", json={"password": "myNewSecret"})

    rows = await _all_audit(db_session)
    for row in rows:
        if row.detail:
            assert "mySecretPass" not in row.detail
            assert "myNewSecret" not in row.detail
