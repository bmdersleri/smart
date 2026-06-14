import asyncio
import logging
from contextlib import asynccontextmanager
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.core.timescaledb import init_timescaledb
from app.api import auth, tags, dashboard, reports
from app.collector.opc_client import collector
from app.collector.poller import poll_loop

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=0.1,
    )
    logger.info("Sentry initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Veritabanı tablolarını oluştur
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await init_timescaledb(conn)
    logger.info("Veritabani tablolari hazir")

    # OPC UA bağlantısı kur
    try:
        await collector.connect()
        poll_task = asyncio.create_task(poll_loop())
        logger.info("OPC UA collector baslatildi")
    except Exception as e:
        logger.warning("OPC UA baglantisi kurulamadi (simülasyon modunda devam): %s", e)
        poll_task = None

    yield

    if poll_task:
        poll_task.cancel()
    await collector.disconnect()


app = FastAPI(
    title="SCADA Reporter",
    description="Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemi",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "opc_connected": collector.client is not None}
