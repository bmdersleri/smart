"""Trend zaman serisi downsample (max_points) + rollup seçimi."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import downsample, pick_rollup
from app.core.security import hash_password
from app.models.user import User


def test_pick_rollup_short_window_uses_raw():
    assert pick_rollup(1) is None
    assert pick_rollup(6) is None


def test_pick_rollup_medium_window_uses_1m():
    assert pick_rollup(24) == "tag_readings_1m"


def test_pick_rollup_multiday_uses_5m():
    assert pick_rollup(72) == "tag_readings_5m"


def test_pick_rollup_long_window_uses_1h():
    assert pick_rollup(720) == "tag_readings_1h"


@pytest.mark.asyncio
async def test_trend_agg_falls_back_to_raw_on_sqlite(client: AsyncClient, db_session: AsyncSession):
    # SQLite'da continuous aggregate view'ı yok -> ham veriye düşer, çökmemeli
    db_session.add(
        User(
            username="agg", email="a@t.com", hashed_password=hash_password("test123"), role="admin"
        )
    )
    await db_session.commit()
    tok = await client.post("/api/auth/token", data={"username": "agg", "password": "test123"})
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}

    tag_r = await client.post(
        "/api/tags/",
        json={"node_id": "AGG,REAL0", "name": "AggTag", "unit": "m3"},
        headers=headers,
    )
    tag_id = tag_r.json()["id"]

    r = await client.get(
        "/api/dashboard/trend_agg",
        params={"tag_ids": [tag_id], "hours": 72},
        headers=headers,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_downsample_returns_all_when_under_limit():
    data = [{"t": str(i), "v": float(i)} for i in range(5)]
    assert downsample(data, 100) == data


def test_downsample_none_limit_returns_all():
    data = [{"t": str(i), "v": float(i)} for i in range(50)]
    assert downsample(data, None) == data


def test_downsample_caps_point_count():
    data = [{"t": str(i), "v": float(i)} for i in range(1000)]
    out = downsample(data, 100)
    assert len(out) <= 100


def test_downsample_keeps_first_and_last():
    data = [{"t": str(i), "v": float(i)} for i in range(1000)]
    out = downsample(data, 100)
    assert out[0] == data[0]
    assert out[-1] == data[-1]
