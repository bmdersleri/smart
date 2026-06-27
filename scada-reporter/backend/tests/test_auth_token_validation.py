"""Direct regression tests for app.api.auth.authenticate_token (Task 6)."""

import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.api.auth import authenticate_token
from app.core.security import create_access_token, hash_password
from app.models.user import User


def _unique(prefix: str = "atv") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_user(
    db_session,
    *,
    username: str,
    password: str = "pass1234",
    role: str = "operator",
    is_active: bool = True,
    token_version: int = 0,
) -> User:
    user = User(
        username=username,
        email=f"{username}@scada.local",
        hashed_password=hash_password(password),
        role=role,
        permission_overrides={},
        is_active=is_active,
        token_version=token_version,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_valid_token_returns_active_user(db_session):
    user = await _create_user(db_session, username=_unique())
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version}
    )

    result = await authenticate_token(token, db_session)

    assert result.id == user.id
    assert result.username == user.username
    assert result.is_active is True


@pytest.mark.asyncio
async def test_invalid_token_returns_401(db_session):
    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token("not-a-jwt", db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Gecersiz token"


@pytest.mark.asyncio
async def test_inactive_user_returns_401(db_session):
    user = await _create_user(db_session, username=_unique(), is_active=False)
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version}
    )

    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token(token, db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Kullanici bulunamadi"


@pytest.mark.asyncio
async def test_token_version_mismatch_returns_401(db_session):
    user = await _create_user(db_session, username=_unique(), token_version=2)
    token = create_access_token({"sub": user.username, "role": user.role, "ver": 1})

    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token(token, db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Token gecersiz (surum)"


@pytest.mark.asyncio
async def test_unknown_scope_returns_401(db_session):
    user = await _create_user(db_session, username=_unique())
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version, "scope": "bogus"}
    )

    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token(token, db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Gecersiz token scope"


@pytest.mark.asyncio
async def test_sse_scoped_token_rejected_by_normal_api_auth(db_session):
    user = await _create_user(db_session, username=_unique())
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version, "scope": "sse"}
    )

    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token(token, db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "SSE token API erisimi icin kullanilamaz"


@pytest.mark.asyncio
async def test_sse_scoped_token_accepted_when_sse_allowed(db_session):
    user = await _create_user(db_session, username=_unique())
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version, "scope": "sse"}
    )

    result = await authenticate_token(token, db_session, sse_allowed=True)

    assert result.id == user.id
    assert result.username == user.username


@pytest.mark.asyncio
async def test_expired_token_returns_401(db_session):
    user = await _create_user(db_session, username=_unique())
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version},
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(HTTPException) as excinfo:
        await authenticate_token(token, db_session)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Gecersiz token"
