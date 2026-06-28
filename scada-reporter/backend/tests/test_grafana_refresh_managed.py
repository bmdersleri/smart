import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _override(role: str):
    fake = User(id=1, username="u", email="u@x.io", hashed_password=hash_password("x"), role=role)
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[require_feature("grafana")] = lambda: None


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_feature("grafana"), None)


def _handler(search_rows, dash_by_uid, posted):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/search":
            return httpx.Response(200, json=search_rows)
        if path.startswith("/api/dashboards/uid/"):
            uid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"dashboard": dash_by_uid[uid]})
        if path == "/api/dashboards/db":
            body = request.read().decode()
            posted.append(body)
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)

    return handler


_NAME_SQL = "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"


@pytest.mark.asyncio
async def test_refresh_updates_managed(client, monkeypatch):
    _override("admin")
    search_rows = [{"uid": "sr-wq-1"}, {"uid": "sr-lab-2-aa"}, {"uid": "sr-rpt-9"}]
    dash_by_uid = {
        "sr-wq-1": {
            "uid": "sr-wq-1",
            "panels": [
                {
                    "targets": [
                        {
                            "rawQueryText": _NAME_SQL,
                            "queryText": _NAME_SQL,
                        }
                    ]
                }
            ],
        },
        "sr-lab-2-aa": {
            "uid": "sr-lab-2-aa",
            "panels": [
                {
                    "targets": [
                        {
                            "rawQueryText": "SELECT time, param_name AS metric, value",
                            "queryText": "SELECT time, param_name AS metric, value",
                        }
                    ]
                }
            ],
        },
        "sr-rpt-9": {
            "uid": "sr-rpt-9",
            "panels": [
                {
                    "targets": [
                        {
                            "rawSql": _NAME_SQL,
                        }
                    ]
                }
            ],
        },
    }
    posted: list[str] = []
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd,
        "_transport",
        httpx.MockTransport(_handler(search_rows, dash_by_uid, posted)),
        raising=False,
    )

    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["updated"] == 2  # sr-wq-1 and sr-rpt-9 changed
    assert any(s["uid"] == "sr-lab-2-aa" for s in data["skipped"])  # lab = no-op
    assert len(posted) == 2
    assert any("COALESCE(NULLIF(t.description" in p for p in posted)


@pytest.mark.asyncio
async def test_refresh_non_admin_403(client, monkeypatch):
    _override("operator")
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd,
        "_transport",
        httpx.MockTransport(lambda req: httpx.Response(200, json=[])),
        raising=False,
    )
    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_grafana_down_502(client, monkeypatch):
    _override("admin")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.post("/api/grafana/dashboards/refresh-managed")
    assert r.status_code == 502
