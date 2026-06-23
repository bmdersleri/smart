import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


async def _admin_token(client: AsyncClient, db: AsyncSession, username: str) -> str:
    db.add(
        User(
            username=username,
            email=f"{username}@t.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db.commit()
    r = await client.post("/api/auth/token", data={"username": username, "password": "pw123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_template_with_grafana_panels_round_trips(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _admin_token(client, db_session, "gf_user1")
    h = {"Authorization": f"Bearer {tok}"}
    payload = {
        "name": "gf-tpl",
        "tag_ids": [1],
        "grafana_panels": [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}],
    }
    r = await client.post("/api/advanced-reports/templates", json=payload, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["grafana_panels"] == payload["grafana_panels"]

    got = await client.get(f"/api/advanced-reports/templates/{body['id']}", headers=h)
    assert got.json()["grafana_panels"] == payload["grafana_panels"]


@pytest.mark.asyncio
async def test_create_template_without_panels_defaults_empty(
    client: AsyncClient, db_session: AsyncSession
):
    tok = await _admin_token(client, db_session, "gf_user2")
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/advanced-reports/templates", json={"name": "no-gf", "tag_ids": [1]}, headers=h
    )
    assert r.status_code == 201, r.text
    assert r.json()["grafana_panels"] == []


@pytest.mark.asyncio
async def test_create_template_rejects_malicious_dashboard_uid_path_traversal(
    client: AsyncClient, db_session: AsyncSession
):
    """dashboard_uid with path traversal chars must return 422 (never stored)."""
    tok = await _admin_token(client, db_session, "gf_user3")
    h = {"Authorization": f"Bearer {tok}"}
    for bad_uid in ["../evil", "../../etc/passwd", "uid/with/slashes", "uid?q=x"]:
        r = await client.post(
            "/api/advanced-reports/templates",
            json={
                "name": "bad-uid",
                "tag_ids": [1],
                "grafana_panels": [{"dashboard_uid": bad_uid, "panel_id": 1, "title": "T"}],
            },
            headers=h,
        )
        assert r.status_code == 422, (
            f"Expected 422 for uid={bad_uid!r}, got {r.status_code}: {r.text}"
        )


@pytest.mark.asyncio
async def test_create_template_rejects_empty_and_overlong_dashboard_uid(
    client: AsyncClient, db_session: AsyncSession
):
    """Empty string and 65-char uid must both return 422."""
    tok = await _admin_token(client, db_session, "gf_user4")
    h = {"Authorization": f"Bearer {tok}"}
    for bad_uid in ["", "a" * 65]:
        r = await client.post(
            "/api/advanced-reports/templates",
            json={
                "name": "bad-uid-len",
                "tag_ids": [1],
                "grafana_panels": [{"dashboard_uid": bad_uid, "panel_id": 1, "title": "T"}],
            },
            headers=h,
        )
        assert r.status_code == 422, (
            f"Expected 422 for uid={bad_uid!r}, got {r.status_code}: {r.text}"
        )
