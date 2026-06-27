import json

import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.lab import LabParameter, LabSamplePoint
from app.models.user import User


@pytest.fixture
def _auth_override():
    fake = User(
        id=1, username="a", email="a@x.io", hashed_password=hash_password("x"), role="admin"
    )
    guard = require_feature("grafana")
    app.dependency_overrides[get_current_user] = lambda: fake
    app.dependency_overrides[guard] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(guard, None)


async def _seed(db):
    point = LabSamplePoint(code="INLET", name="Inlet")
    ph = LabParameter(code="PH", name="pH", min_limit=6.5, max_limit=9.0)
    cod = LabParameter(code="COD", name="COD", unit="mg/L", max_limit=400.0)
    db.add_all([point, ph, cod])
    await db.commit()
    await db.refresh(point)
    await db.refresh(ph)
    await db.refresh(cod)
    return point, ph, cod


@pytest.mark.asyncio
async def test_generate_from_lab_success(client, db_session, monkeypatch, _auth_override):
    point, ph, cod = await _seed(db_session)
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/db":
            posted["json"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "success", "url": "/d/x/lab"})
        return httpx.Response(404)

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id, cod.id]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uid"].startswith(f"sr-lab-{point.id}-")
    assert body["title"] == "Lab — Inlet"
    assert posted["json"]["overwrite"] is True
    assert len(posted["json"]["dashboard"]["panels"]) == 3  # 2 ts + 1 table


@pytest.mark.asyncio
async def test_missing_point_404(client, db_session, monkeypatch, _auth_override):
    _, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False
    )
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": 99999, "parameter_ids": [ph.id]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_empty_params_422(client, db_session, monkeypatch, _auth_override):
    point, _, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False
    )
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_missing_parameter_404(client, db_session, monkeypatch, _auth_override):
    point, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(404)), raising=False
    )
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id, 88888]},
    )
    assert r.status_code == 404
    assert "missing_parameter_ids" in str(r.json()["detail"])


@pytest.mark.asyncio
async def test_grafana_failure_502(client, db_session, monkeypatch, _auth_override):
    point, ph, _ = await _seed(db_session)
    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(
        gd, "_transport", httpx.MockTransport(lambda req: httpx.Response(500)), raising=False
    )
    r = await client.post(
        "/api/grafana/dashboards/from-lab",
        json={"sample_point_id": point.id, "parameter_ids": [ph.id]},
    )
    assert r.status_code == 502
