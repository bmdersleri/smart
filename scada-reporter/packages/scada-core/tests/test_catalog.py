import inspect
from scada_core.catalog import CAPABILITIES, CATALOG


EXPECTED = {
    "query_current_values",
    "query_trend",
    "generate_report",
    "list_tags",
    "list_plcs",
    "run_sql_query",
    "detect_anomalies",
    "predict_trend",
    "get_system_health",
    "resolve_tag",
}


def test_all_capabilities_present():
    assert {c.name for c in CAPABILITIES} == EXPECTED


def test_catalog_integrity():
    for cap in CAPABILITIES:
        assert cap.description.strip(), f"{cap.name} missing description"
        assert cap.input_schema.get("type") == "object", f"{cap.name} bad schema"
        assert inspect.iscoroutinefunction(cap.handler) or callable(cap.handler)


def test_lookup_by_name():
    assert CATALOG["run_sql_query"].name == "run_sql_query"
    assert CATALOG["run_sql_query"].tier == "read"


def test_all_existing_capabilities_are_read_tier():
    for cap in CAPABILITIES:
        assert cap.tier == "read"


def test_tier_values_are_valid():
    for cap in CAPABILITIES:
        assert cap.tier in {"read", "write", "destructive"}
