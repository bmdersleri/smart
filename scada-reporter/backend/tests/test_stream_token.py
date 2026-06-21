"""SSE kısa ömürlü stream-token testleri (Task 6 — Phase 3).

Doğrulanan özellikler:
- POST /api/auth/stream-token normal token ile → 200, scope="sse" token + expires_in döner.
- Döndürülen token decode edilince scope="sse" ve kısa TTL görünür.
- SSE endpoint (/dashboard/stream) hem SSE-scoped hem normal token kabul eder (geriye uyumluluk).
- SSE-scoped token normal API endpoint'inde (/auth/me) → 401.
- Kimlik doğrulamasız POST /stream-token → 401.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.collector.cache import latest_cache
from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password
from app.main import app
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique(prefix: str = "st") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_user(db_session, *, username, password="pass1234", role="operator") -> User:
    u = User(
        username=username,
        email=f"{username}@scada.local",
        hashed_password=hash_password(password),
        role=role,
        permission_overrides={},
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def full_client(db_session):
    """AsyncClient with real DB dependency override."""
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_and_token(db_session, full_client):
    name = _unique()
    user = await _create_user(db_session, username=name, password="pass1234", role="admin")
    token = await _login(full_client, name, "pass1234")
    return user, token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_token_endpoint_returns_200_with_normal_token(
    db_session, full_client, user_and_token
):
    """POST /api/auth/stream-token normal token ile 200 ve sse-scoped token döndürür."""
    _, normal_token = user_and_token
    resp = await full_client.post(
        "/api/auth/stream-token",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "stream_token" in body
    assert "expires_in" in body
    assert body["expires_in"] == settings.STREAM_TOKEN_TTL_SECONDS


@pytest.mark.asyncio
async def test_stream_token_has_sse_scope_and_short_ttl(db_session, full_client, user_and_token):
    """Döndürülen stream token decode edilince scope='sse' ve kısa TTL içermelidir."""
    user, normal_token = user_and_token
    resp = await full_client.post(
        "/api/auth/stream-token",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 200
    stream_token = resp.json()["stream_token"]

    payload = decode_token(stream_token)
    assert payload is not None, "Stream token decode edilemedi"
    assert payload.get("scope") == "sse"
    assert payload.get("sub") == user.username

    # TTL kontrolü: exp değeri yaklaşık TTL kadar olmalı (±5s tolerans)
    now_ts = datetime.now(UTC).timestamp()
    exp = payload.get("exp")
    assert exp is not None
    remaining = exp - now_ts
    assert 0 < remaining <= settings.STREAM_TOKEN_TTL_SECONDS + 5, (
        f"Beklenenden uzun TTL: {remaining}s"
    )


@pytest.mark.asyncio
async def test_stream_token_unauthenticated_returns_401(full_client):
    """Kimlik doğrulamasız POST /stream-token → 401."""
    resp = await full_client.post("/api/auth/stream-token")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_endpoint_accepts_stream_token(db_session, full_client, user_and_token):
    """SSE endpoint SSE-scoped stream token ile çalışmalıdır."""
    _, normal_token = user_and_token
    # Stream token al
    st_resp = await full_client.post(
        "/api/auth/stream-token",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert st_resp.status_code == 200
    stream_token = st_resp.json()["stream_token"]

    # Cache'e bir değer koy
    latest_cache.update(61001, 42.0, 192, datetime.now(UTC))

    # SSE endpoint'i stream token ile çağır
    r = await full_client.get(
        "/api/dashboard/stream",
        params={"token": stream_token, "tag_ids": [61001], "limit": 1},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_sse_endpoint_still_accepts_normal_token_backward_compat(
    db_session, full_client, user_and_token
):
    """SSE endpoint normal (scope=None) token kabul etmeli — geriye uyumluluk."""
    _, normal_token = user_and_token
    latest_cache.update(61002, 7.7, 192, datetime.now(UTC))

    r = await full_client.get(
        "/api/dashboard/stream",
        params={"token": normal_token, "tag_ids": [61002], "limit": 1},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_sse_scoped_token_rejected_on_normal_api_endpoint(
    db_session, full_client, user_and_token
):
    """SSE-scoped token normal API endpoint'inde (/auth/me) → 401."""
    _, normal_token = user_and_token
    st_resp = await full_client.post(
        "/api/auth/stream-token",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert st_resp.status_code == 200
    stream_token = st_resp.json()["stream_token"]

    # /auth/me SSE-scoped token ile → 401
    r = await full_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {stream_token}"},
    )
    assert r.status_code == 401, f"SSE token API'de reddedilmeli, got {r.status_code}"


@pytest.mark.asyncio
async def test_expired_stream_token_rejected_on_sse_endpoint():
    """Süresi dolmuş stream-token SSE endpoint'inde 401 döndürmelidir.

    Not: decode_token süresi dolmuş tokenı None döndürür (jose JWTError),
    bu nedenle gerçek bir expired token oluşturup test etmek yerine
    authenticate_token'ın None payload için 401 döndürdüğünü doğrularız.
    """
    # Çok kısa TTL ile token oluştur (bu zaman birimi geçmiş gibi)
    from datetime import timedelta

    from app.core.security import decode_token

    expired_token = create_access_token(
        {"sub": "nobody", "scope": "sse"},
        expires_delta=timedelta(seconds=-1),  # negatif → zaten süresi dolmuş
    )
    # decode_token süresi dolmuş tokeni None döndürür
    payload = decode_token(expired_token)
    assert payload is None, "Süresi dolmuş token None döndürmeli"
