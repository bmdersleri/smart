import asyncio
import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, dashboard, explore, query, reports, tags
from app.collector.opc_client import collector
from app.collector.opcua_server import opcua_server
from app.collector.poller import poll_loop
from app.core.config import settings
from app.core.database import Base, engine
from app.core.timescaledb import init_timescaledb
from app.models.report_history import ReportHistory as _ReportHistory  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    # Rapor dosyaları için dizin oluştur
    os.makedirs("reports", exist_ok=True)

    # Veritabanı tablolarını oluştur
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await init_timescaledb(conn)
    logger.info("Veritabani tablolari hazir")

    # S7 bağlantısı kur
    try:
        await collector.connect()
        poll_task = asyncio.create_task(poll_loop())
        logger.info("S7 collector baslatildi")
    except Exception as e:
        logger.warning("S7 baglantisi kurulamadi (simulasyon modunda devam): %s", e)
        poll_task = None

    # Dahili OPC UA server
    try:
        await opcua_server.start()
        logger.info("OPC UA server baslatildi")
    except Exception as e:
        logger.warning("OPC UA server baslatilamadi: %s", e)

    yield

    await opcua_server.stop()
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
app.include_router(query.router, prefix="/api")
app.include_router(explore.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "opc_connected": collector.client is not None}
