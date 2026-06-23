from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.pdf_builder import build_pdf


def _tpl():
    return SimpleNamespace(
        name="Test Report",
        interval="hourly",
        show_summary_stats=False,
        show_trend_charts=False,
        show_anomaly_table=False,
        show_raw_data=False,
        include_percentiles=False,
    )


def _archive():
    return SimpleNamespace(
        id=1,
        start=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
    )


def test_build_pdf_accepts_grafana_charts_without_error():
    out = build_pdf(
        _archive(),
        [],
        _tpl(),
        "Tesis",
        datetime.now(UTC),
        lang="en",
        grafana_charts=[{"title": "Debi", "png": b"", "error": "render edilemedi"}],
    )
    assert out[:4] == b"%PDF"


def test_build_pdf_grafana_charts_defaults_none():
    out = build_pdf(_archive(), [], _tpl(), "Tesis", datetime.now(UTC), lang="en")
    assert out[:4] == b"%PDF"
