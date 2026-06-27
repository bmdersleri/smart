from __future__ import annotations

import pytest
from httpx import AsyncClient

import app.api.query as query_api
from app.core.security import create_access_token, hash_password
from app.models.user import User


@pytest.fixture
async def auth_headers(db_session):
    user = User(
        username="query_admin",
        email="query_admin@scada.local",
        hashed_password=hash_password("pass1234"),
        role="admin",
        permission_overrides={},
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(
        {"sub": user.username, "role": user.role, "ver": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


async def _run(client: AsyncClient, headers: dict[str, str], sql: str, *, limit: int = 5000):
    return await client.post("/api/query/run", json={"sql": sql, "limit": limit}, headers=headers)


@pytest.mark.asyncio
async def test_select_query_returns_rows(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "SELECT 1 AS value")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["columns"] == ["value"]
    assert body["rows"] == [{"value": 1}]
    assert body["row_count"] == 1
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_mutating_query_rejected(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "DELETE FROM users")

    assert resp.status_code == 400
    assert "SELECT/WITH/EXPLAIN" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_multi_statement_query_rejected(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "SELECT 1; SELECT 2")

    assert resp.status_code == 400
    assert "Tek sorgu" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trailing_semicolon_is_allowed(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "SELECT 1 AS value;")

    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == [{"value": 1}]


@pytest.mark.asyncio
async def test_semicolon_inside_string_literal_is_allowed(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "SELECT ';' AS value")

    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == [{"value": ";"}]


@pytest.mark.asyncio
async def test_sql_length_limit_rejected(client: AsyncClient, auth_headers, monkeypatch):
    monkeypatch.setattr(query_api.settings, "QUERY_MAX_SQL_CHARS", 8)

    resp = await _run(client, auth_headers, "SELECT 1 AS value")

    assert resp.status_code == 400
    assert "çok uzun" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_limit_must_be_positive(client: AsyncClient, auth_headers):
    resp = await _run(client, auth_headers, "SELECT 1 AS value", limit=0)

    assert resp.status_code == 400
    assert "limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_limit_is_clamped_to_configured_max(client: AsyncClient, auth_headers, monkeypatch):
    monkeypatch.setattr(query_api.settings, "QUERY_MAX_ROWS", 2)

    resp = await _run(
        client,
        auth_headers,
        """
        SELECT 1 AS value
        UNION ALL SELECT 2
        UNION ALL SELECT 3
        """,
        limit=5000,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == [{"value": 1}, {"value": 2}]
    assert body["row_count"] == 2
    assert body["returned_row_count"] == 2
    assert body["minimum_row_count"] == 3
    assert body["row_count_is_exact"] is False
    assert body["truncated"] is True
