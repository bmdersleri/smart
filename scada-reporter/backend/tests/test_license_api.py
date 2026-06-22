"""Integration: /api/license — status, upload (hot-reload), revert."""

import io

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.license import build_license_token, set_active_license
from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(autouse=True)
def _reset_state():
    set_active_license(None)
    yield
    set_active_license(None)


def _keys() -> tuple[str, str]:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        k.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


async def _token(client: AsyncClient, db: AsyncSession, username: str, role: str = "admin") -> str:
    db.add(
        User(
            username=username,
            email=f"{username}@t.com",
            hashed_password=hash_password("pw123"),
            role=role,
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


@pytest.fixture
def _configured_key(monkeypatch) -> str:
    priv, pub = _keys()
    monkeypatch.setattr(settings, "SCADA_LICENSE_PUBLIC_KEY", pub)
    monkeypatch.setattr(settings, "SCADA_LICENSE_ALGORITHMS", "RS256")
    monkeypatch.setattr(settings, "SCADA_LICENSE_FILE", "")
    return priv


# ── status ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_default_unlicensed(client: AsyncClient, db_session: AsyncSession):
    tok = await _token(client, db_session, "ls_get")
    r = await client.get("/api/license", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["mode"] == "unlicensed"


@pytest.mark.asyncio
async def test_get_status_requires_auth(client: AsyncClient):
    r = await client.get("/api/license")
    assert r.status_code == 401


# ── upload (hot-reload) ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_valid_license_activates(
    client: AsyncClient, db_session: AsyncSession, _configured_key: str
):
    tok = await _token(client, db_session, "ls_up")
    h = {"Authorization": f"Bearer {tok}"}
    jwt_token = build_license_token(
        private_key=_configured_key, algorithm="RS256", customer="Uploaded Co", features=["export"]
    )
    files = {"file": ("license.jwt", io.BytesIO(jwt_token.encode()), "application/octet-stream")}
    r = await client.post("/api/license", files=files, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "licensed"
    assert body["customer"] == "Uploaded Co"

    # hot-reload: status endpoint now reflects it without restart
    s = await client.get("/api/license", headers=h)
    assert s.json()["mode"] == "licensed"


@pytest.mark.asyncio
async def test_upload_invalid_license_rejected(
    client: AsyncClient, db_session: AsyncSession, _configured_key: str
):
    tok = await _token(client, db_session, "ls_bad")
    h = {"Authorization": f"Bearer {tok}"}
    files = {"file": ("license.jwt", io.BytesIO(b"not-a-jwt"), "application/octet-stream")}
    r = await client.post("/api/license", files=files, headers=h)
    assert r.status_code == 400
    # state unchanged
    assert (await client.get("/api/license", headers=h)).json()["mode"] == "unlicensed"


@pytest.mark.asyncio
async def test_upload_requires_admin(
    client: AsyncClient, db_session: AsyncSession, _configured_key: str
):
    tok = await _token(client, db_session, "ls_viewer", role="viewer")
    h = {"Authorization": f"Bearer {tok}"}
    jwt_token = build_license_token(private_key=_configured_key, algorithm="RS256", customer="X")
    files = {"file": ("license.jwt", io.BytesIO(jwt_token.encode()), "application/octet-stream")}
    r = await client.post("/api/license", files=files, headers=h)
    assert r.status_code == 403


# ── revert ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_reverts_to_demo(
    client: AsyncClient, db_session: AsyncSession, _configured_key: str
):
    tok = await _token(client, db_session, "ls_del")
    h = {"Authorization": f"Bearer {tok}"}
    jwt_token = build_license_token(private_key=_configured_key, algorithm="RS256", customer="Y")
    files = {"file": ("license.jwt", io.BytesIO(jwt_token.encode()), "application/octet-stream")}
    await client.post("/api/license", files=files, headers=h)

    r = await client.delete("/api/license", headers=h)
    assert r.status_code == 200
    assert r.json()["mode"] == "demo"
