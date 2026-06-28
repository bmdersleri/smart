from app.services.grafana_templates import (
    LabParamSpec,
    apply_metric_display_name,
    build_facility_overview_dashboard,
    build_lab_dashboard,
    build_report_template_dashboard,
    build_water_quality_dashboard,
)

_DISPLAY = "${__field.labels.metric}"


def _panel(dash: dict, title: str) -> dict:
    return next(p for p in dash["panels"] if p["title"] == title)


def _display_name(panel: dict):
    return panel.get("fieldConfig", {}).get("defaults", {}).get("displayName")


# ── generator output ────────────────────────────────────────────────────────


def test_water_quality_trend_has_metric_display_name():
    dash = build_water_quality_dashboard("sr-wq-x", "WQ", [1, 2])
    assert _display_name(_panel(dash, "Su Kalitesi Trendleri")) == _DISPLAY


def test_facility_timeseries_have_no_display_name():
    dash = build_facility_overview_dashboard("sr-fac-x", "FAC")
    # aggregate panels have a single series (no metric column) — must stay default
    assert _display_name(_panel(dash, "Okuma Hacmi")) is None
    assert _display_name(_panel(dash, "BAD Kalite Oranı")) is None


def test_report_template_trend_has_metric_display_name():
    dash = build_report_template_dashboard(
        template_id=7,
        title="R",
        tag_ids=[1, 2],
        time_range_type="last_24h",
        show_trend_charts=True,
        show_summary_stats=False,
        anomaly_enabled=False,
        show_anomaly_table=False,
    )
    assert _display_name(_panel(dash, "Tag Trendleri")) == _DISPLAY


def test_lab_timeseries_has_metric_display_name():
    params = [LabParamSpec(id=1, code="PH", name="pH", unit="", min_limit=6.5, max_limit=8.5)]
    dash = build_lab_dashboard(point_id=3, point_code="P1", point_name="Nokta", params=params)
    ts = next(p for p in dash["panels"] if p["type"] == "timeseries")
    assert _display_name(ts) == _DISPLAY


# ── apply_metric_display_name helper ────────────────────────────────────────


def test_apply_sets_display_name_on_metric_timeseries():
    panel = {"type": "timeseries", "targets": [{"rawQueryText": "SELECT x, foo AS metric, v"}]}
    assert apply_metric_display_name(panel) is True
    assert panel["fieldConfig"]["defaults"]["displayName"] == _DISPLAY


def test_apply_idempotent():
    panel = {"type": "timeseries", "targets": [{"rawSql": "SELECT foo AS metric, v"}]}
    apply_metric_display_name(panel)
    assert apply_metric_display_name(panel) is False


def test_apply_skips_non_timeseries():
    panel = {"type": "table", "targets": [{"rawQueryText": "SELECT foo AS metric, v"}]}
    assert apply_metric_display_name(panel) is False


def test_apply_skips_timeseries_without_metric():
    panel = {"type": "timeseries", "targets": [{"rawQueryText": 'SELECT count(*) AS "Okuma"'}]}
    assert apply_metric_display_name(panel) is False
    assert "fieldConfig" not in panel or "displayName" not in panel.get("fieldConfig", {}).get(
        "defaults", {}
    )
