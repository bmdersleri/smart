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
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[require_feature("grafana")] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    # require_feature returns a new callable each call; clear all overrides added here
    app.dependency_overrides.clear()


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
