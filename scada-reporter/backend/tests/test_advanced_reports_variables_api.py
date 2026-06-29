"""Advanced report templates round-trip selected facility variable ids."""

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
async def test_template_roundtrips_variable_ids(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "var_user1")
    headers = {"Authorization": f"Bearer {tok}"}
    body = {
        "name": "VarTemplate",
        "tag_ids": [],
        "variable_ids": [11, 22],
        "output_format": "json",
    }
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    tid = resp.json()["id"]
    assert resp.json()["variable_ids"] == [11, 22]

    got = await client.get(f"/api/advanced-reports/templates/{tid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["variable_ids"] == [11, 22]


@pytest.mark.asyncio
async def test_template_variable_ids_default_empty(client: AsyncClient, db_session: AsyncSession):
    tok = await _admin_token(client, db_session, "var_user2")
    headers = {"Authorization": f"Bearer {tok}"}
    body = {"name": "NoVars", "tag_ids": [1], "output_format": "json"}
    resp = await client.post("/api/advanced-reports/templates", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["variable_ids"] == []
