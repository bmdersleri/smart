from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def engine_kwargs(url: str) -> dict:
    """Engine parametreleri. sqlite havuz boyutunu desteklemez → atlanır."""
    kw: dict = {"echo": False, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # Poller yazarken okuma isteği gelince "database is locked" yerine bekle.
        kw["connect_args"] = {"timeout": 30}
    else:
        kw["pool_size"] = settings.DB_POOL_SIZE
        kw["max_overflow"] = settings.DB_MAX_OVERFLOW
    return kw


engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs(settings.DATABASE_URL))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        """WAL + busy_timeout: eşzamanlı poller yazısı ile okuma kilidini önle."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
