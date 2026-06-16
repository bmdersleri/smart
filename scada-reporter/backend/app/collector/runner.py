"""Bağımsız collector process'i — poller + dahili OPC UA server.

API'den ayrı çalıştırmak için (decoupled deployment). Aynı TimescaleDB'ye
yazar; API tarafında RUN_COLLECTOR=False ile birden çok API worker'ı PLC'leri
çoğaltmadan ölçeklenir.

Kullanım:
  python -m app.collector.runner
  just run-collector
"""

import asyncio
import logging

from app.collector.opcua_server import opcua_server
from app.collector.poller import poll_loop
from app.collector.s7_collector import plc_manager
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info(
        "Collector process basliyor (poller + OPC UA), tick: %ds", settings.S7_POLL_INTERVAL
    )
    poll_task = asyncio.create_task(poll_loop())

    try:
        await opcua_server.start()
        logger.info("OPC UA server baslatildi")
    except Exception as e:
        logger.warning("OPC UA server baslatilamadi: %s", e)

    try:
        await poll_task
    except asyncio.CancelledError:
        pass
    finally:
        await opcua_server.stop()
        await plc_manager.disconnect_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Collector durduruldu")
