from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.main import app


def _as_user(role, overrides=None):
    return SimpleNamespace(
        id=1, username=role, role=role, permission_overrides=overrides or {}, is_active=True
    )


@pytest_asyncio.fixture
def as_role():
    def _set(role, overrides=None):
        app.dependency_overrides[get_current_user] = lambda: _as_user(role, overrides)

    yield _set
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_viewer_cannot_create_tag(client, as_role):
    as_role("viewer")
    resp = await client.post("/api/tags/", json={"name": "T1"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_create_plc(client, as_role):
    as_role("operator")
    resp = await client.post("/api/plc/", json={"name": "PLC-X", "ip": "10.0.0.9"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_viewer_cannot_create_plc(client, as_role):
    as_role("viewer")
    resp = await client.post("/api/plc/", json={"name": "PLC-Y"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_delete_report_template(client, as_role):
    as_role("operator")
    resp = await client.delete("/api/advanced-reports/templates/999")
    # operator lacks report_template:delete -> 403 BEFORE the 404 lookup
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_with_override_can_delete_report_template(client, as_role):
    as_role("operator", {"report_template:delete": True})
    resp = await client.delete("/api/advanced-reports/templates/999")
    # permission granted -> passes guard, then 404 (no such template)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_cannot_register(client, as_role):
    as_role("operator")
    resp = await client.post(
        "/api/auth/register",
        json={"username": "x", "email": "x@x.com", "password": "secret1"},
    )
    assert resp.status_code == 403
