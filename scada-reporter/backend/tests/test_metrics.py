"""Prometheus metrik kayıtları ve /metrics endpoint'i."""

import pytest
from httpx import AsyncClient
from prometheus_client import REGISTRY

from app.core import metrics


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
