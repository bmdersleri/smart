"""
Tests for the in-process login rate limiter (app/core/rate_limit.py).

Coverage
--------
* /token (form-data) throttled after LOGIN_RATE_LIMIT_MAX failures → 429
* Successful login resets the counter so the next (MAX-1) failures don't 429
* /login (JSON) is rate-limited the same way
* LOGIN_RATE_LIMIT_ENABLED=False → no 429 regardless of failure count
* Retry-After header present on 429

Test isolation is handled by the autouse _isolate_db fixture in conftest.py,
which calls reset_all() before every test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import reset_all
from app.core.security import hash_password
from app.main import app
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def rate_client(db_session):
    """Fresh AsyncClient wired to the test DB session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testclient") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_user(db_session):
    """Create a known user in the test DB."""
    user = User(
        username="ratelimit_user",
        email="rl@test.local",
        hashed_password=hash_password("correct_password"),
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _token_form(username: str, password: str) -> dict:
    return {"data": {"username": username, "password": password}}


def _login_json(username: str, password: str) -> dict:
    return {"json": {"username": username, "password": password}}


# ---------------------------------------------------------------------------
# /token (form-data) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_rate_limit_triggers(rate_client, seed_user, monkeypatch):
    """After MAX failures on /token the next attempt returns 429."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    reset_all()

    for _ in range(3):
        r = await rate_client.post(
            "/api/auth/token", data={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 400

    # 4th attempt should be rate-limited
    r = await rate_client.post(
        "/api/auth/token", data={"username": "ratelimit_user", "password": "wrong"}
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_token_success_resets_counter(rate_client, seed_user, monkeypatch):
    """A successful login clears the counter; subsequent failures restart from zero."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    reset_all()

    # Fail (MAX-1) = 2 times
    for _ in range(2):
        r = await rate_client.post(
            "/api/auth/token", data={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 400

    # Successful login — resets counter
    r = await rate_client.post(
        "/api/auth/token", data={"username": "ratelimit_user", "password": "correct_password"}
    )
    assert r.status_code == 200

    # Now fail (MAX-1) = 2 more times — should still be 400, not 429
    for _ in range(2):
        r = await rate_client.post(
            "/api/auth/token", data={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 400, f"Expected 400 but got {r.status_code}"


# ---------------------------------------------------------------------------
# /login (JSON) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_json_rate_limit_triggers(rate_client, seed_user, monkeypatch):
    """After MAX failures on /login (JSON) the next attempt returns 429."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    reset_all()

    for _ in range(3):
        r = await rate_client.post(
            "/api/auth/login", json={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 401

    r = await rate_client.post(
        "/api/auth/login", json={"username": "ratelimit_user", "password": "wrong"}
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_login_json_success_resets_counter(rate_client, seed_user, monkeypatch):
    """Successful /login resets counter so next (MAX-1) failures are still 401."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    reset_all()

    # Fail (MAX-1) = 2 times
    for _ in range(2):
        r = await rate_client.post(
            "/api/auth/login", json={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 401

    # Successful login
    r = await rate_client.post(
        "/api/auth/login", json={"username": "ratelimit_user", "password": "correct_password"}
    )
    assert r.status_code == 200

    # Fail 2 more — should be 401, not 429
    for _ in range(2):
        r = await rate_client.post(
            "/api/auth/login", json={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 401, f"Expected 401 but got {r.status_code}"


# ---------------------------------------------------------------------------
# ENABLED=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_disabled(rate_client, seed_user, monkeypatch):
    """When LOGIN_RATE_LIMIT_ENABLED=False, many failures never trigger 429."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 2)
    reset_all()

    for _ in range(10):
        r = await rate_client.post(
            "/api/auth/token", data={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 400, f"Expected 400 but got {r.status_code} (limiter disabled)"


@pytest.mark.asyncio
async def test_rate_limit_disabled_json(rate_client, seed_user, monkeypatch):
    """When LOGIN_RATE_LIMIT_ENABLED=False, /login JSON never triggers 429."""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX", 2)
    reset_all()

    for _ in range(10):
        r = await rate_client.post(
            "/api/auth/login", json={"username": "ratelimit_user", "password": "wrong"}
        )
        assert r.status_code == 401, f"Expected 401 but got {r.status_code} (limiter disabled)"
