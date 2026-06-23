import json

import httpx
import pytest

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.security import hash_password
from app.main import app
from app.models.report_template import ReportTemplate
from app.models.tag import Tag
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


async def _mk_template(db, tag_ids):
    t = ReportTemplate(name="Rapor X", tag_ids=json.dumps(tag_ids), grafana_panels="[]")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _mk_tags(db, ids: list[int]):
    """Create active tags with the given IDs in the test DB."""
    for tid in ids:
        tag = Tag(id=tid, node_id=f"ns=2;s=Tag{tid}", name=f"Tag{tid}", is_active=True)
        db.add(tag)
    await db.commit()


@pytest.mark.asyncio
async def test_generate_from_report_template(client, db_session, monkeypatch, _auth_override):
    await _mk_tags(db_session, [1, 2])
    tmpl = await _mk_template(db_session, [1, 2])
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dashboards/db":
            posted["json"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "success", "url": "/d/sr-rpt-1/x"})
        return httpx.Response(404)

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(handler), raising=False)

    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uid"] == f"sr-rpt-{tmpl.id}"
    assert body["template_id"] == tmpl.id
    assert posted["json"]["overwrite"] is True


@pytest.mark.asyncio
async def test_missing_template_404(client, monkeypatch, _auth_override):
    import app.api.grafana_dashboards as gd

    mock = httpx.MockTransport(lambda req: httpx.Response(404))
    monkeypatch.setattr(gd, "_transport", mock, raising=False)
    r = await client.post("/api/grafana/dashboards/from-report-template/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_empty_tags_422(client, db_session, monkeypatch, _auth_override):
    tmpl = await _mk_template(db_session, [])
    import app.api.grafana_dashboards as gd

    mock = httpx.MockTransport(lambda req: httpx.Response(404))
    monkeypatch.setattr(gd, "_transport", mock, raising=False)
    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_grafana_transport_error_502(client, db_session, monkeypatch, _auth_override):
    await _mk_tags(db_session, [1])
    tmpl = await _mk_template(db_session, [1])

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    import app.api.grafana_dashboards as gd

    monkeypatch.setattr(gd, "_transport", httpx.MockTransport(boom), raising=False)
    r = await client.post(f"/api/grafana/dashboards/from-report-template/{tmpl.id}")
    assert r.status_code == 502
