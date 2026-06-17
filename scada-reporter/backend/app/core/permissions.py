"""Yetki kataloğu ve efektif yetki çözümleyici (rol + kullanıcı override)."""

from __future__ import annotations

PERM_TAG_CREATE = "tag:create"
PERM_PLC_MANAGE = "plc:manage"
PERM_REPORT_CREATE = "report_template:create"
PERM_REPORT_EDIT = "report_template:edit"
PERM_REPORT_DELETE = "report_template:delete"

ALL_PERMISSIONS: tuple[str, ...] = (
    PERM_TAG_CREATE,
    PERM_PLC_MANAGE,
    PERM_REPORT_CREATE,
    PERM_REPORT_EDIT,
    PERM_REPORT_DELETE,
)

ROLE_DEFAULTS: dict[str, dict[str, bool]] = {
    "admin": {p: True for p in ALL_PERMISSIONS},
    "operator": {
        PERM_TAG_CREATE: True,
        PERM_PLC_MANAGE: True,
        PERM_REPORT_CREATE: True,
        PERM_REPORT_EDIT: True,
        PERM_REPORT_DELETE: False,
    },
    "viewer": {p: False for p in ALL_PERMISSIONS},
}


def effective_permissions(user) -> set[str]:
    """User'ın efektif yetki kümesi. admin her zaman tam set."""
    if user.role == "admin":
        return set(ALL_PERMISSIONS)
    base = dict(ROLE_DEFAULTS.get(user.role, {p: False for p in ALL_PERMISSIONS}))
    overrides = getattr(user, "permission_overrides", None) or {}
    for key, value in overrides.items():
        if key in ALL_PERMISSIONS:
            base[key] = bool(value)
    return {perm for perm, granted in base.items() if granted}


def user_can(user, perm: str) -> bool:
    return perm in effective_permissions(user)
