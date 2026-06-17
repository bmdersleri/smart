import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_permission_overrides_defaults_to_empty_dict(db_session):
    u = User(
        username="ovr",
        email="ovr@scada.local",
        hashed_password="x",
        role="operator",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.permission_overrides == {}


@pytest.mark.asyncio
async def test_permission_overrides_roundtrip(db_session):
    u = User(
        username="ovr2",
        email="ovr2@scada.local",
        hashed_password="x",
        role="operator",
        permission_overrides={"plc:manage": False},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.permission_overrides == {"plc:manage": False}
