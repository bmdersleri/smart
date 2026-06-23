from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def _auth_override():
    """Bypass authentication and license guard for all tests in this module."""
    fake_user = SimpleNamespace(
        id=1, username="admin", role="admin", permission_overrides={}, is_active=True
    )
    # Capture the guard object so we can pop the exact key — never call .clear()
    # which would wipe conftest's get_db override and break DB-dependent tests.
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[guard] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(guard, None)


@pytest.mark.asyncio
async def test_list_dashboards(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            return httpx.Response(
                200,
                json=[
                    {"uid": "d1", "title": "Ops", "type": "dash-db"},
                ],
            )
        return httpx.Response(404)

    import app.api.grafana as gapi

    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    r = await client.get("/api/grafana/dashboards")
    assert r.status_code == 200, r.text
    assert r.json() == [{"uid": "d1", "title": "Ops"}]


@pytest.mark.asyncio
async def test_list_panels(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/uid/d1":
            return httpx.Response(
                200,
                json={
                    "dashboard": {
                        "panels": [
                            {"id": 1, "title": "Debi", "type": "timeseries"},
                            {"id": 2, "title": "", "type": "row"},  # row → elenir
                            {"id": 3, "title": "Basınç", "type": "stat"},
                        ]
                    }
                },
            )
        return httpx.Response(404)

    import app.api.grafana as gapi

    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    r = await client.get("/api/grafana/dashboards/d1/panels")
    assert r.status_code == 200, r.text
    assert r.json() == [{"id": 1, "title": "Debi"}, {"id": 3, "title": "Basınç"}]


@pytest.mark.asyncio
async def test_list_panels_invalid_uid(client, monkeypatch):
    """Path-traversal / SSRF: invalid uid must be rejected 400 before any network call."""
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    import app.api.grafana as gapi

    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    for bad_uid in ["../search", "foo/../../admin", "uid with spaces", "a" * 65, ""]:
        r = await client.get(f"/api/grafana/dashboards/{bad_uid}/panels")
        assert r.status_code in (400, 404), f"expected 400 for uid={bad_uid!r}, got {r.status_code}"

    # The Grafana mock must never have been called
    assert not called, "Grafana transport was called despite invalid uid — SSRF not blocked"


@pytest.mark.asyncio
async def test_list_panels_grafana_transport_error(client, monkeypatch):
    """A Grafana connectivity failure must surface as 502, not a 500 crash."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    import app.api.grafana as gapi

    monkeypatch.setattr(gapi, "_transport", httpx.MockTransport(handler))

    r = await client.get("/api/grafana/dashboards/d1/panels")
    assert r.status_code == 502, r.text
    assert "Grafana" in r.json()["detail"]
