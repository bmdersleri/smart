from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.api.license_guard import require_writable
from app.main import app


@pytest_asyncio.fixture(autouse=True)
def _auth_override():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="admin", role="admin", permission_overrides={}, is_active=True
    )
    app.dependency_overrides[require_writable] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_writable, None)


def _const_payload(code, value=1.0):
    return {
        "code": code,
        "name": code,
        "description": "",
        "kind": "scalar",
        "unit": "m3/gun",
        "expression": {"op": "const", "value": value},
        "null_policy": "skip",
        "quality_policy": "good_only",
        "default_time_grain": "day",
        "value_type": "number",
    }


@pytest.mark.asyncio
async def test_create_and_get(client):
    resp = await client.post("/api/facility-variables", json=_const_payload("v1"))
    assert resp.status_code == 201
    vid = resp.json()["id"]

    got = await client.get(f"/api/facility-variables/{vid}")
    assert got.status_code == 200
    assert got.json()["code"] == "v1"
    assert got.json()["version"] == 1


@pytest.mark.asyncio
async def test_create_invalid_expression_422(client):
    bad = _const_payload("bad")
    bad["expression"] = {
        "op": "div",
        "args": [{"op": "const", "value": 1}, {"op": "const", "value": 2}],
    }
    resp = await client.post("/api/facility-variables", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_endpoint(client):
    resp = await client.post(
        "/api/facility-variables/validate",
        json={"expression": {"op": "const", "value": 1}, "kind": "scalar"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_preview_scalar(client):
    await client.post("/api/facility-variables", json=_const_payload("p1", 42.0))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.post(
        f"/api/facility-variables/{vid}/preview",
        json={"window": {"type": "month", "year": 2026, "month": 6}, "grain": "day"},
    )
    assert resp.status_code == 200
    assert resp.json()["kind"] == "scalar"
    assert resp.json()["value"] == 42.0


@pytest.mark.asyncio
async def test_preview_bounds_422(client):
    await client.post("/api/facility-variables", json=_const_payload("p2"))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.post(
        f"/api/facility-variables/{vid}/preview",
        json={
            "window": {
                "type": "custom",
                "start": "2026-01-01T00:00:00",
                "end": "2027-01-01T00:00:00",
            },
            "grain": "hour",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_soft_delete(client):
    await client.post("/api/facility-variables", json=_const_payload("d1"))
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.delete(f"/api/facility-variables/{vid}")
    assert resp.status_code == 204
    got = await client.get(f"/api/facility-variables/{vid}")
    assert got.json()["is_active"] is False


@pytest.mark.asyncio
async def test_dependencies_endpoint(client):
    payload = _const_payload("dep1")
    payload["kind"] = "scalar"
    payload["expression"] = {
        "op": "agg",
        "source": {"type": "tag", "tag_id": 5},
        "agg": "delta",
        "window": "day",
    }
    await client.post("/api/facility-variables", json=payload)
    vid = (await client.get("/api/facility-variables")).json()[0]["id"]
    resp = await client.get(f"/api/facility-variables/{vid}/dependencies")
    assert resp.status_code == 200
    deps = resp.json()
    assert any(d["depends_on_type"] == "tag" and d["depends_on_tag_id"] == 5 for d in deps)
