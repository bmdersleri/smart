"""Deadband veri tasarrufu: saf hesap + endpoint (dinamik, DB'den)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import compute_deadband_savings
from app.models.tag import Tag, TagReading


def test_savings_single_tag():
    # 1 saat pencere, 5 sn aralık -> beklenen 720; gerçek 100 -> 620 tasarruf
    out = compute_deadband_savings([{"sample_interval": 5, "actual": 100}], window_seconds=3600)
    assert out["deadband_tags"] == 1
    assert out["expected_rows"] == 720
    assert out["actual_rows"] == 100
    assert out["saved_rows"] == 620
    assert out["savings_pct"] == pytest.approx(86.1, abs=0.1)


def test_savings_empty_returns_none_pct():
    out = compute_deadband_savings([], window_seconds=3600)
    assert out["deadband_tags"] == 0
    assert out["expected_rows"] == 0
    assert out["savings_pct"] is None


def test_savings_clamps_negative():
    # gerçek beklenenden fazlaysa tasarruf 0 (negatif olmaz)
    out = compute_deadband_savings([{"sample_interval": 5, "actual": 9999}], window_seconds=3600)
    assert out["saved_rows"] == 0
    assert out["savings_pct"] == 0.0


def test_savings_guards_zero_interval():
    out = compute_deadband_savings([{"sample_interval": 0, "actual": 10}], window_seconds=60)
    # 0 -> en az 1 sn kabul; beklenen 60
    assert out["expected_rows"] == 60


@pytest.mark.asyncio
async def test_endpoint_only_counts_deadband_tags(client: AsyncClient, db_session: AsyncSession):
    await client.post(
        "/api/auth/register",
        json={"username": "db_sav", "email": "db_sav@t.com", "password": "pw123", "role": "admin"},
    )
    tok = (
        await client.post("/api/auth/token", data={"username": "db_sav", "password": "pw123"})
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    # deadband'li tag (5 sn) + deadband'siz tag
    t_db = Tag(node_id="SAV,DD0", name="WithDB", long_term=True, sample_interval=5, deadband=0.5)
    t_no = Tag(node_id="SAV,DD4", name="NoDB", long_term=True, sample_interval=5, deadband=None)
    db_session.add_all([t_db, t_no])
    await db_session.commit()
    await db_session.refresh(t_db)
    await db_session.refresh(t_no)

    now = datetime.now(UTC)
    for i in range(10):
        db_session.add(
            TagReading(
                tag_id=t_db.id, value=float(i), quality=192, timestamp=now - timedelta(minutes=i)
            )
        )
    await db_session.commit()

    r = await client.get("/api/dashboard/deadband_savings", params={"hours": 1}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["deadband_tags"] == 1  # yalnız deadband'li sayılır
    assert body["actual_rows"] == 10
    assert body["expected_rows"] == 720
    assert body["saved_rows"] == 710
    assert body["savings_pct"] > 90
