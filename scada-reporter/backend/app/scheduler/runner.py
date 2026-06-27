"""Dedicated APScheduler process.

Run this as the single scheduler instance:

    RUN_COLLECTOR=False RUN_SCHEDULER=True python -m app.scheduler.runner

The module is import-safe; nothing starts until ``main()`` is awaited or the
module is executed as ``__main__``.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import settings
from app.services.scheduler import get_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _install_shutdown_handlers(stop_event: asyncio.Event) -> None:
    """Wake the runner on SIGINT/SIGTERM when the platform supports it."""

    def _request_shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: _request_shutdown())


def _validate_settings() -> None:
    errors = settings.config_errors()
    if errors:
        for error in errors:
            logger.error("Yapılandırma hatası: %s", error)
        raise RuntimeError(f"Production yapılandırma hatası: {'; '.join(errors)}")

    if not settings.RUN_SCHEDULER:
        raise RuntimeError("Scheduler runner RUN_SCHEDULER=True ile çalıştırılmalıdır.")

    for warning in settings.config_warnings():
        logger.warning("Yapılandırma uyarısı: %s", warning)


async def main() -> None:
    """Start APScheduler and keep the process alive until interrupted."""

    _validate_settings()

    logger.info(
        "Scheduler process basliyor (RUN_COLLECTOR=%s, RUN_SCHEDULER=%s)",
        settings.RUN_COLLECTOR,
        settings.RUN_SCHEDULER,
    )
    await start_scheduler(settings.DATABASE_URL)
    logger.info("APScheduler baslatildi")

    stop_event = asyncio.Event()
    _install_shutdown_handlers(stop_event)

    try:
        await stop_event.wait()
    finally:
        sched = get_scheduler()
        if sched:
            sched.shutdown(wait=False)
            logger.info("APScheduler kapatildi")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scheduler durduruldu")
