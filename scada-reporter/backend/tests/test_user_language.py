import pytest
from sqlalchemy import select

from app.models.user import User


@pytest.mark.asyncio
async def test_user_defaults_to_english(db_session):
    user = User(username="lang_default", email="ld@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    result = await db_session.execute(select(User).where(User.username == "lang_default"))
    assert result.scalar_one().language == "en"


@pytest.mark.asyncio
async def test_user_language_is_settable(db_session):
    user = User(username="lang_tr", email="lt@example.com", hashed_password="x", language="tr")
    db_session.add(user)
    await db_session.commit()
    result = await db_session.execute(select(User).where(User.username == "lang_tr"))
    assert result.scalar_one().language == "tr"
