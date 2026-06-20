from scada_core import endpoints as ep


def test_write_endpoint_constants():
    assert ep.TAG_IMPORT_CSV == "api/tags/import_csv"
    assert ep.WATCHLIST_ITEM == "api/dashboard/watchlist/{tag_id}"
    assert ep.ANNOTATIONS == "api/annotations/"
    assert ep.ANNOTATION_ITEM == "api/annotations/{annotation_id}"
    assert ep.ADV_TEMPLATES == "api/advanced-reports/templates"
    assert ep.ADV_TEMPLATE_ITEM == "api/advanced-reports/templates/{template_id}"
    assert ep.ADV_TEMPLATE_RUN == "api/advanced-reports/templates/{template_id}/run"
    assert ep.ADV_SCHEDULED == "api/advanced-reports/scheduled"
    assert ep.ADV_SCHEDULED_ITEM == "api/advanced-reports/scheduled/{scheduled_id}"
    assert ep.ADV_SCHEDULED_TOGGLE == "api/advanced-reports/scheduled/{scheduled_id}/toggle"
    assert ep.ADV_ARCHIVE_ITEM == "api/advanced-reports/archive/{archive_id}"
    assert ep.GROUPS == "api/groups/"
    assert ep.GROUP_ITEM == "api/groups/{group_id}"
    assert ep.GROUP_ASSIGN == "api/groups/{group_id}/assign"
    assert ep.GROUP_UNASSIGN == "api/groups/unassign"
    assert ep.PLC_ITEM == "api/plc/{name}"
    assert ep.USERS == "api/users/"
    assert ep.USER_ITEM == "api/users/{user_id}"
    assert ep.USER_PASSWORD == "api/users/{user_id}/password"
