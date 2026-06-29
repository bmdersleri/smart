from types import SimpleNamespace

from app.core import permissions as p


def _user(role: str, overrides: dict | None = None):
    # SimpleNamespace stands in for the User ORM object — only .role and
    # .permission_overrides are read by the resolver.
    return SimpleNamespace(role=role, permission_overrides=overrides or {})


def test_catalog_keys_exact():
    assert set(p.ALL_PERMISSIONS) == {
        "tag:create",
        "plc:manage",
        "report_template:create",
        "report_template:edit",
        "report_template:delete",
        "facility_variable:create",
        "facility_variable:edit",
        "facility_variable:delete",
    }


def test_admin_has_all_permissions():
    assert p.effective_permissions(_user("admin")) == set(p.ALL_PERMISSIONS)


def test_admin_overrides_ignored():
    # Even an override that revokes is ignored for admin.
    u = _user("admin", {"plc:manage": False})
    assert p.user_can(u, "plc:manage") is True


def test_operator_defaults():
    u = _user("operator")
    assert p.user_can(u, "tag:create") is True
    assert p.user_can(u, "plc:manage") is True
    assert p.user_can(u, "report_template:create") is True
    assert p.user_can(u, "report_template:edit") is True
    assert p.user_can(u, "report_template:delete") is False


def test_viewer_defaults_none():
    u = _user("viewer")
    assert p.effective_permissions(u) == set()


def test_override_grants_extra():
    u = _user("operator", {"report_template:delete": True})
    assert p.user_can(u, "report_template:delete") is True


def test_override_revokes():
    u = _user("operator", {"plc:manage": False})
    assert p.user_can(u, "plc:manage") is False


def test_unknown_override_key_ignored():
    u = _user("operator", {"bogus:perm": True})
    assert p.user_can(u, "bogus:perm") is False


def test_unknown_role_has_no_permissions():
    u = _user("ghost")
    assert p.effective_permissions(u) == set()


def test_facility_variable_perms_registered():
    for perm in (
        p.PERM_FACILITY_VARIABLE_CREATE,
        p.PERM_FACILITY_VARIABLE_EDIT,
        p.PERM_FACILITY_VARIABLE_DELETE,
    ):
        assert perm in p.ALL_PERMISSIONS


def test_facility_variable_role_defaults():
    admin = p.effective_permissions(_user("admin"))
    assert {
        p.PERM_FACILITY_VARIABLE_CREATE,
        p.PERM_FACILITY_VARIABLE_EDIT,
        p.PERM_FACILITY_VARIABLE_DELETE,
    } <= admin

    operator = p.effective_permissions(_user("operator"))
    assert p.PERM_FACILITY_VARIABLE_CREATE in operator
    assert p.PERM_FACILITY_VARIABLE_EDIT in operator
    assert p.PERM_FACILITY_VARIABLE_DELETE not in operator

    viewer = p.effective_permissions(_user("viewer"))
    assert p.PERM_FACILITY_VARIABLE_CREATE not in viewer
