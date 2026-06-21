"""Tests for the JSON /api/auth/login endpoint (Task 3).

TDD: write failing tests first, then implement the endpoint.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


async def _create_user(db: AsyncSession, password: str = "secret123") -> tuple[str, str]:
    """Insert a fresh user and return (username, password)."""
    suffix = uuid.uuid4().hex[:8]
    username = f"jtest_{suffix}"
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password(password),
        full_name="JSON Test User",
        role="operator",
    )
    db.add(user)
    await db.commit()
    return username, password


# ---------------------------------------------------------------------------
# /api/auth/login — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_json_correct_credentials_returns_200(
    client: AsyncClient, db_session: AsyncSession
):
    username, password = await _create_user(db_session)
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 10  # sanity: non-empty JWT


# ---------------------------------------------------------------------------
# /api/auth/login — error paths (must be 401, not 400)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_json_wrong_password_returns_401(client: AsyncClient, db_session: AsyncSession):
    username, _ = await _create_user(db_session)
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "WRONGPASSWORD"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_json_unknown_username_returns_401(
    client: AsyncClient, db_session: AsyncSession
):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "no_such_user_xyz", "password": "whatever"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/token (form-data) — regression guard — must stay 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_form_data_still_works(client: AsyncClient, db_session: AsyncSession):
    username, password = await _create_user(db_session)
    resp = await client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# Both endpoints return the SAME TokenResponse shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_endpoints_return_same_token_response_shape(
    client: AsyncClient, db_session: AsyncSession
):
    username, password = await _create_user(db_session)

    json_resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    form_resp = await client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )

    assert json_resp.status_code == 200
    assert form_resp.status_code == 200

    json_body = json_resp.json()
    form_body = form_resp.json()

    # Same keys
    assert set(json_body.keys()) == {"access_token", "token_type"}
    assert set(form_body.keys()) == {"access_token", "token_type"}

    # Same token_type value
    assert json_body["token_type"] == form_body["token_type"] == "bearer"
