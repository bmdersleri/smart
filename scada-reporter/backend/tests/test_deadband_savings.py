"""Deadband veri tasarrufu: saf hesap + endpoint (dinamik, DB'den)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import compute_deadband_savings
from app.core.security import hash_password
from app.models.tag import Tag, TagReading
from app.models.user import User


def test_savings_single_tag():
    # 1 saat etkin süre, 5 sn aralık -> beklenen 720; gerçek 100 -> 620 tasarruf
    out = compute_deadband_savings(
        [{"sample_interval": 5, "actual": 100, "effective_seconds": 3600}]
    )
    assert out["deadband_tags"] == 1
    assert out["expected_rows"] == 720
    assert out["actual_rows"] == 100
    assert out["saved_rows"] == 620
    assert out["savings_pct"] == pytest.approx(86.1, abs=0.1)


def test_savings_per_tag_span():
    # Her tag KENDİ etkin süresine göre beklenir: A 540 sn (5 sn -> 108),
    # B 180 sn (5 sn -> 36); toplam beklenen 144. Tek global span (540)
    # kullanılsaydı B de 108 sayılır, toplam 216 (yanlış, B'yi şişirir).
    out = compute_deadband_savings(
        [
            {"sample_interval": 5, "actual": 20, "effective_seconds": 540},
            {"sample_interval": 5, "actual": 10, "effective_seconds": 180},
        ]
    )
    assert out["expected_rows"] == 144
    assert out["actual_rows"] == 30
    assert out["saved_rows"] == 114  # (108-20) + (36-10)
    assert out["savings_pct"] == pytest.approx(79.2, abs=0.1)


def test_savings_no_readings_no_fake_savings():
    # Pencerede hiç kaydı olmayan deadband tag'i (effective 0) sahte
    # tasarruf üretmemeli — beklenen 0, tasarruf 0.
    out = compute_deadband_savings([{"sample_interval": 5, "actual": 0, "effective_seconds": 0}])
    assert out["expected_rows"] == 0
    assert out["saved_rows"] == 0
    assert out["savings_pct"] is None


def test_savings_empty_returns_none_pct():
    out = compute_deadband_savings([])
    assert out["deadband_tags"] == 0
    assert out["expected_rows"] == 0
    assert out["savings_pct"] is None


def test_savings_clamps_negative():
    # gerçek beklenenden fazlaysa tasarruf 0 (negatif olmaz)
    out = compute_deadband_savings(
        [{"sample_interval": 5, "actual": 9999, "effective_seconds": 3600}]
    )
    assert out["saved_rows"] == 0
    assert out["savings_pct"] == 0.0


def test_savings_guards_zero_interval():
    out = compute_deadband_savings([{"sample_interval": 0, "actual": 10, "effective_seconds": 60}])
    # 0 -> en az 1 sn kabul; beklenen 60
    assert out["expected_rows"] == 60


@pytest.mark.asyncio
async def test_endpoint_only_counts_deadband_tags(client: AsyncClient, db_session: AsyncSession):
    db_session.add(
        User(
            username="db_sav",
            email="db_sav@t.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db_session.commit()
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
    # Veri yalnız 9 dk yayılıyor → etkin pencere 540 sn, nominal 3600 değil
    assert body["effective_seconds"] == 540
    assert body["expected_rows"] == 108  # 540 / 5 sn
    assert body["saved_rows"] == 98
    assert body["savings_pct"] > 90


@pytest.mark.asyncio
async def test_endpoint_per_tag_spans(client: AsyncClient, db_session: AsyncSession):
    """İki deadband tag'i farklı yayılımda → her biri KENDİ span'ine göre beklenir."""
    # Endpoint global toplar; testler arası izolasyon olmadığından önceki
    # testlerden sızan tag/okumaları temizle (sıraya bağımlı olmamak için).
    await db_session.execute(delete(TagReading))
    await db_session.execute(delete(Tag))
    await db_session.commit()
    db_session.add(
        User(
            username="db_span",
            email="db_span@t.com",
            hashed_password=hash_password("pw123"),
            role="admin",
        )
    )
    await db_session.commit()
    tok = (
        await client.post("/api/auth/token", data={"username": "db_span", "password": "pw123"})
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    t_a = Tag(node_id="SPAN,DD0", name="WideA", long_term=True, sample_interval=5, deadband=0.5)
    t_b = Tag(node_id="SPAN,DD4", name="NarrowB", long_term=True, sample_interval=5, deadband=0.5)
    db_session.add_all([t_a, t_b])
    await db_session.commit()
    await db_session.refresh(t_a)
    await db_session.refresh(t_b)

    now = datetime.now(UTC)
    # A: 9 dk yayılım (dakika 0..9) → span 540 sn → beklenen 108, gerçek 10, tasarruf 98
    for i in range(10):
        db_session.add(
            TagReading(
                tag_id=t_a.id, value=float(i), quality=192, timestamp=now - timedelta(minutes=i)
            )
        )
    # B: 3 dk yayılım (dakika 0..3) → span 180 sn → beklenen 36, gerçek 4, tasarruf 32
    for i in range(4):
        db_session.add(
            TagReading(
                tag_id=t_b.id, value=float(i), quality=192, timestamp=now - timedelta(minutes=i)
            )
        )
    await db_session.commit()

    body = (
        await client.get("/api/dashboard/deadband_savings", params={"hours": 1}, headers=h)
    ).json()
    assert body["deadband_tags"] == 2
    assert body["actual_rows"] == 14
    # Per-tag: 108 + 36 = 144 (tek global span 540 olsaydı 108+108=216 olurdu)
    assert body["expected_rows"] == 144
    assert body["saved_rows"] == 130  # 98 + 32
    assert body["effective_seconds"] == 540  # temsili = en uzun span
