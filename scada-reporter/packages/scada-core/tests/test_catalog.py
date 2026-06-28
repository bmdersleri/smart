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
    "update_tag",
    "delete_tag",
    "watchlist_add",
    "watchlist_remove",
    "annotation_add",
    "annotation_delete",
    "template_create",
    "template_update",
    "template_run",
    "template_delete",
    "scheduled_create",
    "scheduled_update",
    "scheduled_toggle",
    "scheduled_delete",
    "archive_delete",
    "group_create",
    "group_update",
    "group_assign",
    "group_unassign",
    "group_delete",
    "plc_create",
    "plc_update",
    "plc_delete",
    "user_create",
    "user_update",
    "user_set_password",
    "user_delete",
    "compliance_overview",
    "compliance_list_events",
    "compliance_evaluate",
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
    # Spec 2 Task 3: read-only capabilities remain read; write/destructive are new
    read_only = {
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
    for cap in CAPABILITIES:
        if cap.name in read_only:
            assert cap.tier == "read", f"{cap.name} should be read"


def test_tier_values_are_valid():
    for cap in CAPABILITIES:
        assert cap.tier in {"read", "write", "destructive"}
