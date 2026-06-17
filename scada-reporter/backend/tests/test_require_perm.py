from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.auth import require_perm


def _user(role, overrides=None):
    return SimpleNamespace(role=role, permission_overrides=overrides or {})


@pytest.mark.asyncio
async def test_require_perm_allows_permitted_user():
    dep = require_perm("plc:manage")
    user = _user("operator")
    assert await dep(user=user) is user


@pytest.mark.asyncio
async def test_require_perm_blocks_unpermitted_user():
    dep = require_perm("report_template:delete")
    user = _user("operator")  # operator lacks delete
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_perm_admin_always_allowed():
    dep = require_perm("report_template:delete")
    assert await dep(user=_user("admin")) is not None
