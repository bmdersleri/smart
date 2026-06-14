import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_login_register(client: AsyncClient):
    register_resp = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "test123",
            "full_name": "Test User",
            "role": "admin",
        },
    )
    assert register_resp.status_code == 201

    login_resp = await client.post(
        "/api/auth/token",
        data={
            "username": "testuser",
            "password": "test123",
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    assert token


@pytest.mark.asyncio
async def test_me(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={
            "username": "meuser",
            "email": "me@example.com",
            "password": "test123",
            "full_name": "Me User",
        },
    )
    login_resp = await client.post(
        "/api/auth/token",
        data={
            "username": "meuser",
            "password": "test123",
        },
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "meuser"
