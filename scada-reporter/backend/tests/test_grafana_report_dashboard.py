from app.services.grafana_templates import (
    build_report_template_dashboard,
    report_dashboard_uid,
    resolve_dashboard_time,
)


def test_report_dashboard_uid_deterministic():
    assert report_dashboard_uid(7) == "sr-rpt-7"


def test_resolve_time_presets():
    assert resolve_dashboard_time("last_1h", None, None) == {"from": "now-1h", "to": "now"}
    assert resolve_dashboard_time("last_24h", None, None) == {"from": "now-24h", "to": "now"}
    assert resolve_dashboard_time("last_7d", None, None) == {"from": "now-7d", "to": "now"}
    assert resolve_dashboard_time("last_30d", None, None) == {"from": "now-30d", "to": "now"}


def test_resolve_time_custom():
    from datetime import UTC, datetime

    s = datetime(2026, 1, 1, tzinfo=UTC)
    e = datetime(2026, 1, 2, tzinfo=UTC)
    out = resolve_dashboard_time("custom", s, e)
    assert out["from"] == s.isoformat()
    assert out["to"] == e.isoformat()


def _kw(**over):
    base = dict(
        template_id=3,
        title="Rapor X",
        tag_ids=[1, 2],
        time_range_type="last_7d",
        custom_start=None,
        custom_end=None,
        show_trend_charts=True,
        show_summary_stats=True,
        anomaly_enabled=True,
        show_anomaly_table=True,
    )
    base.update(over)
    return base


def test_all_flags_produce_three_panel_types():
    d = build_report_template_dashboard(**_kw())
    assert d["uid"] == "sr-rpt-3"
    assert d["title"] == "Rapor X"
    assert d["time"] == {"from": "now-7d", "to": "now"}
    types = [p["type"] for p in d["panels"]]
    assert "timeseries" in types  # trend
    assert types.count("table") == 2  # summary + anomaly
    # tag filter present in trend SQL, int-coerced
    trend = next(p for p in d["panels"] if p["type"] == "timeseries")
    assert "1, 2" in trend["targets"][0]["rawSql"]


def test_only_trend_flag_yields_single_panel():
    d = build_report_template_dashboard(
        **_kw(show_summary_stats=False, anomaly_enabled=False, show_anomaly_table=False)
    )
    assert [p["type"] for p in d["panels"]] == ["timeseries"]


def test_no_flags_still_has_trend_panel():
    d = build_report_template_dashboard(
        **_kw(
            show_trend_charts=False,
            show_summary_stats=False,
            anomaly_enabled=False,
            show_anomaly_table=False,
        )
    )
    assert any(p["type"] == "timeseries" for p in d["panels"])
    assert len(d["panels"]) >= 1


_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def test_report_template_uses_description_label():
    dash = build_report_template_dashboard(
        template_id=7,
        title="R",
        tag_ids=[1, 2],
        time_range_type="last_24h",
        show_trend_charts=True,
        show_summary_stats=True,
        anomaly_enabled=True,
        show_anomaly_table=True,
    )
    sql = " ".join(t.get("rawSql", "") for p in dash["panels"] for t in p.get("targets", []))
    assert f"{_LABEL} AS metric" in sql
    assert f'SELECT DISTINCT ON (t.id) {_LABEL} AS "Etiket"' in sql
    assert f'{_LABEL} AS "Etiket"' in sql  # breach
    assert "t.name AS metric" not in sql
