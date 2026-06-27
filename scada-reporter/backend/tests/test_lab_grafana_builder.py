import pytest

from app.services.grafana_templates import (
    LabParamSpec,
    build_lab_dashboard,
    lab_dashboard_uid,
)


def _params():
    return [
        LabParamSpec(id=10, code="PH", name="pH", unit="", min_limit=6.5, max_limit=9.0),
        LabParamSpec(id=20, code="COD", name="COD", unit="mg/L", min_limit=None, max_limit=400.0),
    ]


def test_uid_is_deterministic_and_order_independent():
    a = lab_dashboard_uid(5, [20, 10])
    b = lab_dashboard_uid(5, [10, 20])
    assert a == b
    assert a.startswith("sr-lab-5-")
    # different point or param set -> different uid
    assert lab_dashboard_uid(6, [10, 20]) != a
    assert lab_dashboard_uid(5, [10]) != a


def test_build_lab_dashboard_shape():
    dash = build_lab_dashboard(point_id=5, point_code="INLET", point_name="Inlet", params=_params())
    assert dash["uid"] == lab_dashboard_uid(5, [10, 20])
    assert dash["title"] == "Lab — Inlet"
    # one timeseries panel per param + one table panel
    types = [p["type"] for p in dash["panels"]]
    assert types.count("timeseries") == 2
    assert types.count("table") == 1
    # every target uses the timescaledb postgres datasource and queries the view
    for panel in dash["panels"]:
        assert panel["datasource"] == {"type": "postgres", "uid": "timescaledb"}
        sql = panel["targets"][0]["rawSql"]
        assert "v_lab_timeseries" in sql
    # the pH panel filters by its own codes
    ph = next(p for p in dash["panels"] if p["title"].startswith("pH"))
    ph_sql = ph["targets"][0]["rawSql"]
    assert "point_code = 'INLET'" in ph_sql
    assert "param_code = 'PH'" in ph_sql


def test_limits_become_threshold_lines():
    dash = build_lab_dashboard(point_id=5, point_code="INLET", point_name="Inlet", params=_params())
    ph = next(p for p in dash["panels"] if p["title"].startswith("pH"))
    steps = ph["fieldConfig"]["defaults"]["thresholds"]["steps"]
    values = [s["value"] for s in steps]
    assert 6.5 in values and 9.0 in values
    assert ph["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] == {"mode": "line"}
    # COD has only a max limit -> only that line (plus the base None step)
    cod = next(p for p in dash["panels"] if p["title"].startswith("COD"))
    cod_values = [s["value"] for s in cod["fieldConfig"]["defaults"]["thresholds"]["steps"]]
    assert 400.0 in cod_values
    assert 6.5 not in cod_values


def test_bad_code_raises():
    with pytest.raises(ValueError):
        build_lab_dashboard(
            point_id=1,
            point_code="IN'LET",  # quote -> allowlist violation
            point_name="x",
            params=_params(),
        )


def test_empty_params_raises():
    with pytest.raises(ValueError):
        build_lab_dashboard(point_id=1, point_code="INLET", point_name="x", params=[])


def test_lab_sql_code_allowlist():
    from app.services.grafana_templates import _lab_sql_code

    assert _lab_sql_code("a-b_1") == "'a-b_1'"
    for bad in ["a'b", "a b", "a;b", ""]:
        with pytest.raises(ValueError):
            _lab_sql_code(bad)


def test_lab_dashboard_time_window():
    dash = build_lab_dashboard(point_id=5, point_code="INLET", point_name="Inlet", params=_params())
    assert dash["time"] == {"from": "now-30d", "to": "now"}
