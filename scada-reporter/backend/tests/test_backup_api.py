"""Integration tests for /api/backup endpoints (Task 5).

Auth pattern: mirrors test_api.py — _make_user + _login helpers with the
session-scoped `client` + `db_session` fixtures from conftest.py.

Monkeypatching: each test that calls POST /api/backup must monkeypatch BOTH
  settings.BACKUP_DIR  → tmp dir so we don't litter the working tree
  settings.DATABASE_URL → a real on-disk sqlite file that backup_engine can
                          VACUUM INTO (the test suite uses an in-memory engine
                          that is NOT backed by a file, so we supply a seeded
                          temp file as the "live" DB to snapshot).
The Backup metadata row still goes into the in-memory test session (correct).
"""

import sqlite3

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers (same pattern as test_api.py / test_license_api.py)
# ---------------------------------------------------------------------------


async def _make_user(db: AsyncSession, username: str, role: str) -> None:
    db.add(
        User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=hash_password("pw123"),
            role=role,
        )
    )
    await db.commit()


async def _login(client: AsyncClient, username: str) -> str:
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_live_db(path) -> str:
    """Create a minimal sqlite file that backup_engine can VACUUM INTO."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE t(x)")
    con.commit()
    con.close()
    return f"sqlite+aiosqlite:///{path}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_backup(
    client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch
):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))

    await _make_user(db_session, "bk_admin1", "admin")
    tok = await _login(client, "bk_admin1")

    r = await client.post("/api/backup", headers=_auth(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "verified"
    assert body["sha256"]
    assert body["trigger"] == "manual"
    assert body["kind"] == "full"

    lst = await client.get("/api/backup", headers=_auth(tok))
    assert lst.status_code == 200
    assert len(lst.json()) == 1


@pytest.mark.asyncio
async def test_create_backup_requires_admin(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_op1", "operator")
    tok = await _login(client, "bk_op1")

    r = await client.post("/api/backup", headers=_auth(tok))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_backup(client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))

    await _make_user(db_session, "bk_admin2", "admin")
    tok = await _login(client, "bk_admin2")

    created = (await client.post("/api/backup", headers=_auth(tok))).json()
    assert created["status"] == "verified"

    d = await client.delete(f"/api/backup/{created['id']}", headers=_auth(tok))
    assert d.status_code == 200
    assert d.json()["deleted"] == created["id"]

    lst = await client.get("/api/backup", headers=_auth(tok))
    assert lst.json() == []


@pytest.mark.asyncio
async def test_list_requires_admin(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_op2", "operator")
    tok = await _login(client, "bk_op2")

    r = await client.get("/api/backup", headers=_auth(tok))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_download_not_found(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_admin3", "admin")
    tok = await _login(client, "bk_admin3")

    r = await client.get("/api/backup/99999/download", headers=_auth(tok))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_admin4", "admin")
    tok = await _login(client, "bk_admin4")

    r = await client.delete("/api/backup/99999", headers=_auth(tok))
    assert r.status_code == 404
