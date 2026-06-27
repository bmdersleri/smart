import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _override(role: str):
    fake = User(id=1, username="u", email="u@x.io", hashed_password=hash_password("x"), role=role)
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[guard] = lambda: None


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_feature("grafana"), None)


@pytest.mark.asyncio
async def test_admin_deletes_dashboard(client, monkeypatch):
    _override("admin")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"message": "Dashboard deleted"})

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.delete("/api/grafana/dashboards/sr-lab-5-abc123de")
    assert r.status_code == 200, r.text
    assert r.json() == {"uid": "sr-lab-5-abc123de", "status": "deleted"}
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/dashboards/uid/sr-lab-5-abc123de"


@pytest.mark.asyncio
async def test_invalid_uid_422_no_grafana_call(client, monkeypatch):
    _override("admin")
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    # a/b would traverse the Grafana path; %2e etc. also rejected by the allowlist
    r = await client.delete("/api/grafana/dashboards/a..b")
    assert r.status_code == 422
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_grafana_404(client, monkeypatch):
    _override("admin")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/missinguid")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_provisioned_409(client, monkeypatch):
    _override("admin")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(412)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/labquality")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_403(client, monkeypatch):
    _override("operator")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(200)), raising=False
    )
    r = await client.delete("/api/grafana/dashboards/sr-rpt-1")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_transport_error_502(client, monkeypatch):
    _override("admin")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.delete("/api/grafana/dashboards/sr-rpt-1")
    assert r.status_code == 502
