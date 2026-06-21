"""Tests for seed_users.main() and seed_tags.main() against the test DB.

The seed functions use AsyncSessionLocal (the app's own session factory).
We monkeypatch that factory to point at the in-memory test engine so the
seeds operate on the same isolated DB that the rest of the test suite uses.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.seed_tags as seed_tags_mod
import app.seed_users as seed_users_mod
from app.models.tag import Tag
from app.models.user import User


@pytest.mark.asyncio
async def test_seed_users_main_creates_admin_and_operator(db_engine, monkeypatch):
    """seed_users.main() creates admin + operator when DB is empty."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    # Redirect AsyncSessionLocal used inside main() to the test engine
    monkeypatch.setattr(seed_users_mod, "AsyncSessionLocal", sm)

    await seed_users_mod.main()

    async with sm() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

    usernames = {u.username for u in users}
    assert "admin" in usernames
    assert "operator" in usernames
    assert len(users) == 2


@pytest.mark.asyncio
async def test_seed_users_main_idempotent(db_engine, monkeypatch):
    """Calling seed_users.main() twice results in exactly 2 users (no duplicates)."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(seed_users_mod, "AsyncSessionLocal", sm)

    await seed_users_mod.main()
    await seed_users_mod.main()  # second call should be a no-op

    async with sm() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

    assert len(users) == 2


@pytest.mark.asyncio
async def test_seed_tags_main_creates_tags(db_engine, monkeypatch):
    """seed_tags.main() creates expected tags when DB is empty."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(seed_tags_mod, "AsyncSessionLocal", sm)

    await seed_tags_mod.main()

    async with sm() as db:
        result = await db.execute(select(Tag))
        tags = result.scalars().all()

    # The seed file defines TAGS — we just check there are some
    assert len(tags) == len(seed_tags_mod.TAGS)
    node_ids = {t.node_id for t in tags}
    # Spot-check a few known node IDs from the seed data
    assert "DB171,REAL0" in node_ids
    assert "DB177,REAL0" in node_ids


@pytest.mark.asyncio
async def test_seed_tags_main_idempotent(db_engine, monkeypatch):
    """Calling seed_tags.main() twice produces no duplicate tags."""
    sm = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(seed_tags_mod, "AsyncSessionLocal", sm)

    await seed_tags_mod.main()
    await seed_tags_mod.main()

    async with sm() as db:
        result = await db.execute(select(Tag))
        tags = result.scalars().all()

    assert len(tags) == len(seed_tags_mod.TAGS)
