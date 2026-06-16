import pytest
from httpx import AsyncClient


async def _get_token(client: AsyncClient, suffix: str) -> str:
    """Register a fresh user and return a Bearer token."""
    await client.post(
        "/api/auth/register",
        json={
            "username": f"languser_{suffix}",
            "email": f"languser_{suffix}@example.com",
            "password": "test123",
            "full_name": "Lang User",
        },
    )
    login_resp = await client.post(
        "/api/auth/token",
        data={"username": f"languser_{suffix}", "password": "test123"},
    )
    return login_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_me_returns_language(client: AsyncClient):
    token = await _get_token(client, "me")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["language"] == "en"


@pytest.mark.asyncio
async def test_patch_me_updates_language(client: AsyncClient):
    token = await _get_token(client, "patch")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.patch("/api/auth/me", json={"language": "tr"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["language"] == "tr"
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["language"] == "tr"


@pytest.mark.asyncio
async def test_patch_me_rejects_unknown_language(client: AsyncClient):
    token = await _get_token(client, "reject")
    resp = await client.patch(
        "/api/auth/me",
        json={"language": "xx"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
