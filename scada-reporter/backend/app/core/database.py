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


def set_sqlite_pragmas(dbapi_conn) -> None:  # type: ignore[no-untyped-def]
    """Her SQLite bağlantısı için performans + eşzamanlılık pragmaları.

    WAL + busy_timeout: poller yazarken okuma "database is locked" yerine bekler.
    synchronous=NORMAL: WAL ile güvenli, FULL'den hızlı.
    cache_size=-64000: 64 MB sayfa önbelleği (negatif = KB cinsinden).
    mmap_size=256 MB: bellek-eşlemeli okuma, syscall'ı azaltır.
    wal_autocheckpoint=1000: ~1000 sayfada checkpoint → WAL dosyası şişmez.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA cache_size=-64000")
    cur.execute("PRAGMA mmap_size=268435456")
    cur.execute("PRAGMA wal_autocheckpoint=1000")
    cur.close()


if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        set_sqlite_pragmas(dbapi_conn)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
