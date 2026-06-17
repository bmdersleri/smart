"""Prometheus metrik kayıtları ve /metrics endpoint'i."""

import pytest
from httpx import AsyncClient
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.security import hash_password
from app.models.user import User


def _sample(name: str, labels: dict | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_add_rows_written_increments():
    before = _sample("scada_rows_written_total")
    metrics.add_rows_written(3)
    assert _sample("scada_rows_written_total") - before == 3.0


def test_add_bad_quality_increments():
    before = _sample("scada_bad_quality_total")
    metrics.add_bad_quality(2)
    assert _sample("scada_bad_quality_total") - before == 2.0


def test_observe_tick_records_count_and_sum():
    before = _sample("scada_tick_duration_seconds_count")
    metrics.observe_tick(0.5)
    assert _sample("scada_tick_duration_seconds_count") - before == 1.0


def test_observe_plc_read_labeled_by_plc():
    metrics.observe_plc_read("10.0.0.99", 0.1)
    assert _sample("scada_plc_read_seconds_count", {"plc": "10.0.0.99"}) == 1.0


def test_render_returns_text_with_metric_names():
    metrics.add_rows_written(1)
    out = metrics.render().decode()
    assert "scada_rows_written_total" in out
    assert "scada_tick_duration_seconds" in out


@pytest.mark.asyncio
async def test_metrics_endpoint_serves_prometheus(client: AsyncClient):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "scada_rows_written_total" in resp.text
    assert resp.headers["content-type"].startswith("text/plain")


def test_summary_has_keys_and_reflects_counters():
    before = metrics.summary()["rows_written_total"]
    metrics.add_rows_written(5)
    s = metrics.summary()
    assert s["rows_written_total"] - before == 5.0
    for key in ("rows_written_total", "bad_quality_total", "tick_avg_seconds", "plcs"):
        assert key in s
    assert isinstance(s["plcs"], list)


def test_summary_per_plc_avg():
    metrics.observe_plc_read("10.7.7.7", 0.2)
    metrics.observe_plc_read("10.7.7.7", 0.4)
    s = metrics.summary()
    row = next(p for p in s["plcs"] if p["plc"] == "10.7.7.7")
    assert row["count"] >= 2
    assert row["avg_seconds"] is not None and row["avg_seconds"] > 0


@pytest.mark.asyncio
async def test_metrics_summary_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/dashboard/metrics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_metrics_summary_endpoint_returns_json(client: AsyncClient, db_session: AsyncSession):
    db_session.add(
        User(
            username="mx", email="mx@t.com", hashed_password=hash_password("test123"), role="admin"
        )
    )
    await db_session.commit()
    tok = await client.post("/api/auth/token", data={"username": "mx", "password": "test123"})
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    resp = await client.get("/api/dashboard/metrics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "rows_written_total" in data
    assert "plcs" in data


@pytest.mark.asyncio
async def test_metrics_summary_enriches_plc_name_and_tag_count(
    client: AsyncClient, db_session: AsyncSession
):
    db_session.add(
        User(
            username="mn", email="mn@t.com", hashed_password=hash_password("test123"), role="admin"
        )
    )
    await db_session.commit()
    tok = await client.post("/api/auth/token", data={"username": "mn", "password": "test123"})
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}

    for i in range(2):
        await client.post(
            "/api/tags/",
            json={
                "node_id": f"PN{i},REAL0",
                "name": f"PN{i}",
                "plc_ip": "10.5.5.5",
                "plc_name": "TESTPLC",
            },
            headers=headers,
        )
    metrics.observe_plc_read("10.5.5.5", 0.1)

    data = (await client.get("/api/dashboard/metrics", headers=headers)).json()
    row = next(p for p in data["plcs"] if p["plc"] == "10.5.5.5")
    assert row["name"] == "TESTPLC"
    assert row["tag_count"] == 2
