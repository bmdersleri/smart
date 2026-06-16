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

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "meuser"


@pytest.mark.asyncio
async def test_patch_tag_alarm_thresholds(client: AsyncClient):
    # Create a tag first
    await client.post(
        "/api/auth/register",
        json={
            "username": "patchuser",
            "email": "p@test.com",
            "password": "test123",
            "role": "admin",
        },
    )
    token_r = await client.post(
        "/api/auth/token", data={"username": "patchuser", "password": "test123"}
    )
    token = token_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    tag_r = await client.post(
        "/api/tags/",
        json={"node_id": "DB99,REAL0", "name": "PatchTest", "unit": "m3/h"},
        headers=headers,
    )
    assert tag_r.status_code == 201
    tag_id = tag_r.json()["id"]

    # PATCH alarm thresholds
    patch_r = await client.patch(
        f"/api/tags/{tag_id}", json={"min_alarm": 0.0, "max_alarm": 5000.0}, headers=headers
    )
    assert patch_r.status_code == 200
    data = patch_r.json()
    assert data["min_alarm"] == 0.0
    assert data["max_alarm"] == 5000.0

    # PATCH unit only
    patch_r2 = await client.patch(f"/api/tags/{tag_id}", json={"unit": "bar"}, headers=headers)
    assert patch_r2.status_code == 200
    assert patch_r2.json()["unit"] == "bar"
    assert patch_r2.json()["max_alarm"] == 5000.0  # unchanged


@pytest.mark.asyncio
async def test_patch_tag_deadband(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "dbuser", "email": "db@test.com", "password": "test123", "role": "admin"},
    )
    token_r = await client.post(
        "/api/auth/token", data={"username": "dbuser", "password": "test123"}
    )
    headers = {"Authorization": f"Bearer {token_r.json()['access_token']}"}

    tag_r = await client.post(
        "/api/tags/",
        json={"node_id": "DB88,REAL0", "name": "DeadbandTag", "unit": "m3/h"},
        headers=headers,
    )
    assert tag_r.status_code == 201
    tag_id = tag_r.json()["id"]
    assert tag_r.json()["deadband"] is None

    patch_r = await client.patch(f"/api/tags/{tag_id}", json={"deadband": 2.5}, headers=headers)
    assert patch_r.status_code == 200
    assert patch_r.json()["deadband"] == 2.5


@pytest.mark.asyncio
async def test_report_history(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={
            "username": "histuser",
            "email": "h@test.com",
            "password": "test123",
            "role": "admin",
        },
    )
    token_r = await client.post(
        "/api/auth/token", data={"username": "histuser", "password": "test123"}
    )
    headers = {"Authorization": f"Bearer {token_r.json()['access_token']}"}

    # History starts empty
    hist_r = await client.get("/api/reports/history", headers=headers)
    assert hist_r.status_code == 200
    assert hist_r.json() == []

    # Generate a JSON report
    gen_r = await client.post(
        "/api/reports/generate",
        json={
            "tag_ids": [],
            "start": "2026-01-01T00:00:00",
            "end": "2026-01-02T00:00:00",
            "interval": "hourly",
            "format": "json",
        },
        headers=headers,
    )
    assert gen_r.status_code == 200

    # History now has 1 entry
    hist_r2 = await client.get("/api/reports/history", headers=headers)
    assert len(hist_r2.json()) == 1
    entry = hist_r2.json()[0]
    assert entry["format"] == "json"
    assert entry["interval"] == "hourly"
