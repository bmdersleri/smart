from types import SimpleNamespace

import pytest

from app.api.auth import get_current_user
from app.main import app


def _user(role: str, uid: int = 1):
    return SimpleNamespace(
        id=uid, username=f"{role}{uid}", role=role, permission_overrides={}, is_active=True
    )


def _as(role: str, uid: int = 1):
    app.dependency_overrides[get_current_user] = lambda: _user(role, uid)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_creates_approved_parameter(client):
    _as("admin")
    resp = await client.post("/api/lab/parameters", json={"code": "PH", "name": "pH"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["approved"] is True
    assert body["code"] == "PH"


@pytest.mark.asyncio
async def test_operator_created_parameter_is_unapproved(client):
    _as("operator", uid=5)
    resp = await client.post(
        "/api/lab/parameters", json={"code": "COD", "name": "COD", "unit": "mg/L"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["approved"] is False


@pytest.mark.asyncio
async def test_admin_approves_parameter(client):
    _as("operator", uid=5)
    created = (await client.post("/api/lab/parameters", json={"code": "TSS", "name": "TSS"})).json()
    _as("admin")
    resp = await client.patch(
        f"/api/lab/parameters/{created['id']}", json={"approved": True, "max_limit": 30.0}
    )
    assert resp.status_code == 200
    assert resp.json()["approved"] is True
    assert resp.json()["max_limit"] == 30.0


@pytest.mark.asyncio
async def test_list_filters_approved(client):
    _as("operator", uid=5)
    await client.post("/api/lab/parameters", json={"code": "P1", "name": "P1"})  # unapproved
    _as("admin")
    await client.post("/api/lab/parameters", json={"code": "P2", "name": "P2"})  # approved
    resp = await client.get("/api/lab/parameters?approved=true")
    codes = [p["code"] for p in resp.json()]
    assert "P2" in codes and "P1" not in codes


@pytest.mark.asyncio
async def test_operator_cannot_patch_parameter(client):
    _as("admin")
    created = (await client.post("/api/lab/parameters", json={"code": "X", "name": "X"})).json()
    _as("operator", uid=5)
    resp = await client.patch(f"/api/lab/parameters/{created['id']}", json={"name": "Y"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sample_point_crud(client):
    _as("admin")
    created = (
        await client.post("/api/lab/sample-points", json={"code": "INLET", "name": "Inlet"})
    ).json()
    assert created["approved"] is True
    resp = await client.delete(f"/api/lab/sample-points/{created['id']}")
    assert resp.status_code == 204
