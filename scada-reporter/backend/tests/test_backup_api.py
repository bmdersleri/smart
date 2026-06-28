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

import asyncio
import sqlite3

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.api.backup as backup_mod
import app.core.database as database_mod
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


def _patch_bg(monkeypatch, db_engine) -> None:
    """Redirect the background job's own session factory to the test engine so its
    writes land in the same in-memory DB the test session reads."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_mod, "AsyncSessionLocal", factory)


async def _drain() -> None:
    """Await all in-flight backup/restore background tasks."""
    while backup_mod._tasks:
        await asyncio.gather(*list(backup_mod._tasks), return_exceptions=True)


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
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_admin1", "admin")
    tok = await _login(client, "bk_admin1")

    # POST returns 202 immediately with a 'running' record; work runs in background.
    r = await client.post("/api/backup", headers=_auth(tok))
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    assert body["kind"] == "full"

    await _drain()

    lst = await client.get("/api/backup", headers=_auth(tok))
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "verified"
    assert rows[0]["sha256"]
    assert rows[0]["filename"].endswith(".db.zst")
    # created_at must carry an explicit UTC offset (frontend renders local time)
    assert rows[0]["created_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_create_backup_requires_admin(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_op1", "operator")
    tok = await _login(client, "bk_op1")

    r = await client.post("/api/backup", headers=_auth(tok))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_backup(
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_admin2", "admin")
    tok = await _login(client, "bk_admin2")

    created = (await client.post("/api/backup", headers=_auth(tok))).json()
    assert created["status"] == "running"
    await _drain()

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


@pytest.mark.asyncio
async def test_restore_requires_confirm(
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_admin5", "admin")
    tok = await _login(client, "bk_admin5")
    admin_headers = _auth(tok)

    created = (await client.post("/api/backup", headers=admin_headers)).json()
    await _drain()
    bad = await client.post(
        f"/api/backup/{created['id']}/restore",
        json={"confirm": "nope"},
        headers=admin_headers,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_restore_requires_admin(client: AsyncClient, db_session: AsyncSession):
    await _make_user(db_session, "bk_op3", "operator")
    tok = await _login(client, "bk_op3")

    r = await client.post(
        "/api/backup/1/restore",
        json={"confirm": "RESTORE"},
        headers=_auth(tok),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_backup_filenames_unique(
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    """I3: two backups created in the same second must produce different filenames."""
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_uniq_admin", "admin")
    tok = await _login(client, "bk_uniq_admin")

    r1 = await client.post("/api/backup", headers=_auth(tok))
    assert r1.status_code == 202, r1.text
    r2 = await client.post("/api/backup", headers=_auth(tok))
    assert r2.status_code == 202, r2.text
    await _drain()

    from sqlalchemy import select

    from app.models.backup import Backup

    rows = (await db_session.execute(select(Backup))).scalars().all()
    names = {r.filename for r in rows}
    assert len(names) == 2, f"Two backup filenames must differ (id suffix missing?): {names}"


@pytest.mark.asyncio
async def test_restore_failure_records_failed_progress_and_safety_snapshot(
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    """On a background restore RuntimeError: progress key reaches status 'failed'
    and a safety snapshot row was still created beforehand."""
    from app.services import backup_progress as bp

    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_restore_fail_admin", "admin")
    tok = await _login(client, "bk_restore_fail_admin")
    headers = _auth(tok)

    # Create the backup to restore
    created = (await client.post("/api/backup", headers=headers)).json()
    await _drain()
    backup_id = created["id"]

    # Monkeypatch restore_snapshot to simulate a catastrophic failure
    def _boom(**kwargs):  # noqa: ANN202
        raise RuntimeError("boom")

    monkeypatch.setattr(backup_mod.be, "restore_snapshot", _boom)

    r = await client.post(
        f"/api/backup/{backup_id}/restore",
        json={"confirm": "RESTORE"},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    await _drain()

    prog = bp.get(f"restore-{backup_id}")
    assert prog is not None and prog["status"] == "failed"
    assert "boom" in (prog["error"] or "")

    # A second (safety) backup row must have been created before the failure
    from sqlalchemy import select

    from app.models.backup import Backup

    rows = (await db_session.execute(select(Backup))).scalars().all()
    assert len(rows) >= 2, f"Expected at least 2 backup rows (original + safety), got {len(rows)}"


@pytest.mark.asyncio
async def test_progress_endpoint_streams_terminal_frame(
    client: AsyncClient, db_session: AsyncSession, db_engine, tmp_path, monkeypatch
):
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))
    _patch_bg(monkeypatch, db_engine)

    await _make_user(db_session, "bk_prog_admin", "admin")
    tok = await _login(client, "bk_prog_admin")
    headers = _auth(tok)

    created = (await client.post("/api/backup", headers=headers)).json()
    await _drain()

    stream_tok = (await client.post("/api/auth/stream-token", headers=headers)).json()[
        "stream_token"
    ]
    r = await client.get(f"/api/backup/{created['id']}/progress?token={stream_tok}")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert '"status": "done"' in r.text


@pytest.mark.asyncio
async def test_progress_endpoint_rejects_bad_token(client: AsyncClient, db_session: AsyncSession):
    r = await client.get("/api/backup/1/progress?token=garbage")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_scheduled_backup_runs(tmp_path, monkeypatch, db_session, db_engine):
    """scheduled_backup_job() creates a verified scheduled backup row.

    Visibility approach: scheduled_backup_job opens its own session via
    AsyncSessionLocal (local import from app.core.database). We patch
    app.core.database.AsyncSessionLocal to a session factory bound to the
    same in-memory test engine (db_engine) so the job's writes are visible
    to db_session. We also patch settings.DATABASE_URL to a real temp sqlite
    file because backup_engine.create_snapshot uses VACUUM INTO which requires
    a file-backed source DB.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.core.database as database_mod
    from app.core.config import settings
    from app.services.scheduler import scheduled_backup_job

    # Redirect the session factory the job opens to use the test engine.
    test_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_mod, "AsyncSessionLocal", test_session_factory)

    # Provide a real sqlite file as the "live DB" for VACUUM INTO.
    live = tmp_path / "live.db"
    monkeypatch.setattr(settings, "DATABASE_URL", _seed_live_db(live))
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "bk"))

    await scheduled_backup_job()  # must not raise; creates a verified backup row

    from sqlalchemy import select

    from app.models.backup import Backup

    rows = (await db_session.execute(select(Backup))).scalars().all()
    assert any(r.trigger == "scheduled" and r.status == "verified" for r in rows)
