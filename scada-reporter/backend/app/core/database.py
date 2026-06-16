from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def engine_kwargs(url: str) -> dict:
    """Engine parametreleri. sqlite havuz boyutunu desteklemez → atlanır."""
    kw: dict = {"echo": False, "pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kw["pool_size"] = settings.DB_POOL_SIZE
        kw["max_overflow"] = settings.DB_MAX_OVERFLOW
    return kw


engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs(settings.DATABASE_URL))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
