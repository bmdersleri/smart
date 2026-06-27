import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api import (
    advanced_reports,
    ai,
    annotations,
    audit,
    auth,
    dashboard,
    excel_templates,
    explore,
    grafana,
    grafana_dashboards,
    groups,
    plc,
    query,
    realtime,
    reports,
    tags,
    users,
    watchlist_groups,
)
from app.api import (
    health as health_router,  # liveness/readiness — mounted without /api prefix
)
from app.api import (
    license as license_api,
)
from app.collector.opcua_server import opcua_server
from app.collector.poller import poll_loop
from app.collector.s7_collector import plc_manager
from app.core import metrics
from app.core.config import settings
from app.core.database import Base, engine
from app.core.license import initialize_license_state
from app.core.log_buffer import log_buffer
from app.core.timescaledb import (
    init_continuous_aggregates,
    init_daily_rollup,
    init_timescaledb,
)
from app.models import annotation as _annotation  # noqa: F401
from app.models import audit_log as _audit_log  # noqa: F401
from app.models import excel_template as _excel_template  # noqa: F401
from app.models import lab as _lab  # noqa: F401
from app.models import plc_health as _plc_health  # noqa: F401
from app.models import plc_incident as _plc_incident  # noqa: F401
from app.models import report_archive, report_template, scheduled_report  # noqa: F401
from app.models import tag_group as _tag_group  # noqa: F401
from app.models import watchlist_group as _watchlist_group  # noqa: F401
from app.models.report_history import ReportHistory as _ReportHistory  # noqa: F401
from app.services.scheduler import get_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
log_buffer.setLevel(logging.INFO)
logging.getLogger().addHandler(log_buffer)

# Gürültülü 3. parti logger'ları kıs — canlı konsol sinyalini koru.
# asyncua açılışta yüzlerce "add_node" INFO basar; snap7 her tick connect/disconnect.
logging.getLogger("asyncua").setLevel(logging.WARNING)
logging.getLogger("snap7").setLevel(logging.WARNING)

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=0.1,
    )
    logger.info("Sentry initialized")


async def init_database_schema(conn) -> None:
    """create_all yalnız AUTO_CREATE_TABLES ise; init_timescaledb her zaman (idempotent)."""
    if settings.AUTO_CREATE_TABLES:
        await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info("AUTO_CREATE_TABLES=False — şema Alembic'ten bekleniyor (alembic upgrade head)")
    await init_timescaledb(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prod yapılandırma sağlık kontrolü — tehlikeli varsayılanlarda durdur
    errors = settings.config_errors()
    if errors:
        for e in errors:
            logger.error("Yapılandırma hatası: %s", e)
        raise RuntimeError(f"Production yapılandırma hatası: {'; '.join(errors)}")

    for w in settings.config_warnings():
        logger.warning("Yapılandırma uyarısı: %s", w)

    license_state = initialize_license_state(settings)
    if license_state.info:
        logger.info(
            "Commercial license verified: customer=%s license_id=%s",
            license_state.info.customer or "-",
            license_state.info.license_id or "-",
        )
    else:
        logger.info("License mode: %s", license_state.mode.value)

    # Rapor dosyaları için dizin oluştur
    os.makedirs("reports", exist_ok=True)

    # Veritabanı tablolarını oluştur
    async with engine.begin() as conn:
        await init_database_schema(conn)
    logger.info("Veritabani tablolari hazir")

    # Sürekli toplama view'ları ayrı AUTOCOMMIT bağlantısında (CAGG DDL transaction'sız)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await init_continuous_aggregates(conn)
        await init_daily_rollup(conn)

    await start_scheduler(settings.DATABASE_URL)
    logger.info("APScheduler baslatildi")

    # Collector (poller + OPC UA) yalnız RUN_COLLECTOR ise bu process'te çalışır.
    # API'yi collector'dan ayırmak için API worker'larında RUN_COLLECTOR=False
    # kullanın (çoklu PLC okumasını çoğaltmamak için). Ayrı collector process:
    # python -m app.collector.runner
    poll_task: asyncio.Task | None = None
    opcua_task: asyncio.Task | None = None
    monitor_task: asyncio.Task | None = None
    if settings.RUN_COLLECTOR:
        poll_task = asyncio.create_task(poll_loop())
        logger.info("S7 poller baslatildi (coklu PLC, lazy connect)")

        async def _start_opcua() -> None:
            try:
                await opcua_server.start()
                logger.info("OPC UA server baslatildi")
            except Exception as e:
                logger.warning("OPC UA server baslatilamadi: %s", e)

        opcua_task = asyncio.create_task(_start_opcua())

        from app.monitor.monitor import plc_monitor_loop

        monitor_task = asyncio.create_task(plc_monitor_loop())
        logger.info("PLC monitor baslatildi")
    else:
        logger.info("RUN_COLLECTOR=False — collector bu process'te baslatilmadi")

    yield

    sched = get_scheduler()
    if sched:
        sched.shutdown(wait=False)
    if monitor_task:
        monitor_task.cancel()
    if opcua_task:
        opcua_task.cancel()
        await opcua_server.stop()
    if poll_task:
        poll_task.cancel()
        await plc_manager.disconnect_all()


app = FastAPI(
    title="EKONT SMART REPORT",
    description="Su/Atıksu tesisi SCADA veri toplama ve raporlama sistemi",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next):
    """Record HTTP request count and latency in Prometheus metrics."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    method = request.method
    status = str(response.status_code)
    metrics.http_requests_total.labels(method=method, status=status).inc()
    metrics.http_request_duration.labels(method=method).observe(duration)
    return response


# Liveness / readiness — mounted WITHOUT /api prefix so they are at /live and /ready.
app.include_router(health_router.router)

app.include_router(auth.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(realtime.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(explore.router, prefix="/api")
app.include_router(advanced_reports.router, prefix="/api")
app.include_router(excel_templates.router, prefix="/api")
app.include_router(plc.router, prefix="/api")
app.include_router(groups.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(watchlist_groups.router, prefix="/api")
app.include_router(grafana_dashboards.router, prefix="/api")
app.include_router(grafana.router, prefix="/api")
app.include_router(license_api.router, prefix="/api")


@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=metrics.render(), media_type=metrics.CONTENT_TYPE)


@app.get("/health")
async def health():
    plc_status = plc_manager.status()
    sched = get_scheduler()
    return {
        "status": "ok",
        "plc_connected": sum(1 for v in plc_status.values() if v),
        "plc_total": len(plc_status),
        "plcs": plc_status,
        "collector_running": settings.RUN_COLLECTOR,
        "scheduler_running": sched is not None and getattr(sched, "running", False),
        "uptime_seconds": metrics.uptime_seconds(),
        "started_at": metrics.process_started_at().isoformat(),
    }
