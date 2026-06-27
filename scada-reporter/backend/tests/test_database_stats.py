from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api.auth import get_current_user
from app.main import app
from app.models.tag import Tag, TagReading


def _as_user():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="u", role="operator", permission_overrides={}, is_active=True
    )


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_database_stats_empty(client):
    _as_user()
    r = await client.get("/api/dashboard/database")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_readings"] == 0
    assert body["total_is_estimate"] is False  # SQLite (dev) = tam count
    assert body["earliest"] is None
    assert body["est_monthly_growth_bytes"] == 0
    assert body["size_bytes"] >= 0
    names = {t["name"] for t in body["tables"]}
    assert "tag_readings" in names and "tags" in names


@pytest.mark.asyncio
async def test_database_stats_counts(client, db_session):
    tag = Tag(node_id="n1", name="T1")
    db_session.add(tag)
    await db_session.flush()
    now = datetime.utcnow()
    db_session.add(TagReading(tag_id=tag.id, value=1.0, quality=192, timestamp=now))
    db_session.add(
        TagReading(tag_id=tag.id, value=2.0, quality=192, timestamp=now - timedelta(days=10))
    )
    await db_session.commit()

    _as_user()
    r = await client.get("/api/dashboard/database")
    body = r.json()
    assert body["total_readings"] == 2
    assert body["total_is_estimate"] is False
    assert body["last_day"] == 1  # only the recent row
    assert body["last_month"] == 2  # both within 30 days
    assert body["tag_count"] == 1
    assert body["earliest"] is not None
    tr = next(t for t in body["tables"] if t["name"] == "tag_readings")
    assert tr["rows"] == 2
