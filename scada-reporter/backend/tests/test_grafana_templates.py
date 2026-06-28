import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.tag import Tag
from app.models.user import User
from app.services.grafana_templates import (
    build_dashboard,
    build_facility_overview_dashboard,
    build_report_template_dashboard,
    build_water_quality_dashboard,
    dashboard_uid,
    list_templates,
)

_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def _all_sql(dash: dict) -> str:
    return " ".join(
        t.get("rawQueryText", "") + " " + t.get("queryText", "")
        for p in dash["panels"]
        for t in p.get("targets", [])
    )


def test_water_quality_uses_description_label():
    dash = build_water_quality_dashboard("sr-wq-x", "WQ", [1, 2])
    sql = _all_sql(dash)
    # trend series label
    assert f"{_LABEL} AS metric" in sql
    # latest-values table: inner label + outer readable header
    assert f"{_LABEL} AS name" in sql
    assert 'name AS "Etiket"' in sql
    # breach table header
    assert f'{_LABEL} AS "Etiket"' in sql
    # grouping stays per-tag
    assert "GROUP BY t.name" in sql
    # no bare technical-name label remains
    assert "t.name AS metric" not in sql


def test_facility_overview_uses_description_label():
    dash = build_facility_overview_dashboard("sr-fac-x", "FAC")
    sql = _all_sql(dash)
    assert f"{_LABEL} AS name" in sql
    assert 'name AS "Etiket"' in sql


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
    assert dashboard["time"] == {"from": "now-7d", "to": "now"}
    trend = dashboard["panels"][0]
    assert trend["datasource"]["type"] == "frser-sqlite-datasource"
    assert trend["datasource"]["uid"] == settings.GRAFANA_DATASOURCE_UID
    sql = trend["targets"][0]["queryText"]
    assert "tr.tag_id IN (1, 2)" in sql
    assert "$__" not in sql
    assert "strftime('%s'" in sql
    assert "datetime('now', '-7 days')" in sql
    # latest-values table uses a window function, not DISTINCT ON
    table_sql = dashboard["panels"][1]["targets"][0]["queryText"]
    assert "row_number()" in table_sql
    assert "DISTINCT ON" not in table_sql


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


def test_build_facility_dashboard_is_frser():
    dash = build_dashboard("facility_overview", "sr-fac-x", "Tesis")
    assert "facility-overview" in dash["tags"]
    for panel in dash["panels"]:
        assert panel["datasource"]["type"] == "frser-sqlite-datasource"
        assert panel["datasource"]["uid"] == settings.GRAFANA_DATASOURCE_UID
        tgt = panel["targets"][0]
        assert "$__" not in tgt["queryText"]
        assert "now() - INTERVAL" not in tgt["queryText"]
        assert "EXTRACT(EPOCH" not in tgt["queryText"]
    sqls = {p["title"]: p["targets"][0]["queryText"] for p in dash["panels"]}
    assert "/ 300) * 300 AS time" in sqls["Okuma Hacmi"]
    assert "datetime('now', '-24 hours')" in sqls["Okuma Hacmi"]
    assert "row_number()" in sqls["Son Değerler"]
    assert "DISTINCT ON" not in sqls["Son Değerler"]


def test_report_template_dashboard_still_postgres():
    dash = build_report_template_dashboard(
        template_id=1,
        title="Rapor",
        tag_ids=[1, 2],
        time_range_type="last_24h",
        show_trend_charts=True,
        show_summary_stats=True,
        anomaly_enabled=False,
        show_anomaly_table=False,
    )
    trend = dash["panels"][0]
    assert trend["datasource"] == {"type": "postgres", "uid": "timescaledb"}
    assert "$__timeFilter" in trend["targets"][0]["rawSql"]
