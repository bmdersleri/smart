import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User
from app.services.grafana_templates import build_dashboard, dashboard_uid, list_templates


async def _auth(client: AsyncClient, db_session: AsyncSession, uname: str = "grafana"):
    db_session.add(
        User(
            username=uname,
            email=f"{uname}@t.com",
            hashed_password=hash_password("test123"),
            role="admin",
        )
    )
    await db_session.commit()
    token = await client.post("/api/auth/token", data={"username": uname, "password": "test123"})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_lists_project_dashboard_templates():
    templates = list_templates()
    keys = {item["key"] for item in templates}
    assert {"facility_overview", "water_quality"} <= keys
    assert any(item["requires_tags"] for item in templates if item["key"] == "water_quality")


def test_build_water_quality_dashboard_shape():
    uid = dashboard_uid("water_quality", 3, "Su Kalitesi Hat 1", [2, 1])
    dashboard = build_dashboard("water_quality", uid, "Su Kalitesi Hat 1", [2, 1])
    assert dashboard["uid"] == uid
    assert "water-quality" in dashboard["tags"]
    sql = dashboard["panels"][0]["targets"][0]["rawSql"]
    assert "tr.tag_id IN (1, 2)" in sql
    assert "$__timeFilter" in sql
    assert dashboard["panels"][0]["datasource"]["uid"] == "timescaledb"


def test_water_quality_requires_tags():
    with pytest.raises(ValueError):
        build_dashboard("water_quality", "uid", "Boş", [])


@pytest.mark.asyncio
async def test_generate_dashboard_endpoint_writes_to_grafana(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    from app.api import grafana_dashboards

    headers = await _auth(client, db_session)
    tag = Tag(node_id="N1", name="pH", unit="pH", is_active=True)
    db_session.add(tag)
    await db_session.commit()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/api/dashboards/db"
        return httpx.Response(200, json={"status": "success", "url": "/d/generated"})

    real_async_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler), base_url="http://gf")

    monkeypatch.setattr(grafana_dashboards.httpx, "AsyncClient", fake_client)

    response = await client.post(
        "/api/grafana/dashboards/generate",
        json={"template": "water_quality", "title": "Su Kalitesi", "tag_ids": [tag.id]},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "/d/generated"
    assert body["template"] == "water_quality"
    assert calls


@pytest.mark.asyncio
async def test_generate_dashboard_requires_tags_for_water_quality(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _auth(client, db_session, "grafana2")
    response = await client.post(
        "/api/grafana/dashboards/generate",
        json={"template": "water_quality", "title": "Su Kalitesi", "tag_ids": []},
        headers=headers,
    )
    assert response.status_code == 422
