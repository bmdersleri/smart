from types import SimpleNamespace

import pytest

from app.api.auth import get_current_user
from app.main import app


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_settings_default_when_unset(client):
    _as("operator")
    r = await client.get("/api/settings")
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "Europe/Istanbul"


@pytest.mark.asyncio
async def test_admin_sets_timezone_then_get_returns_it(client):
    _as("admin")
    put = await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    assert put.status_code == 200, put.text
    assert put.json()["timezone"] == "UTC"
    _as("operator")
    got = await client.get("/api/settings")
    assert got.json()["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_invalid_timezone_422(client):
    _as("admin")
    r = await client.put("/api/settings/timezone", json={"timezone": "Mars/Phobos"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_put_403(client):
    _as("operator")
    r = await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_set_timezone_is_upsert(client):
    _as("admin")
    await client.put("/api/settings/timezone", json={"timezone": "UTC"})
    await client.put("/api/settings/timezone", json={"timezone": "Europe/Berlin"})
    _as("operator")
    got = await client.get("/api/settings")
    assert got.json()["timezone"] == "Europe/Berlin"
