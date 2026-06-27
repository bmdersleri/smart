from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.collector.opcua_server import opcua_server
from app.collector.poller import poll_loop
from app.collector.s7_collector import plc_manager
from app.core import metrics
from app.core.config import settings
from app.services.scheduler import get_scheduler, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def _task_running(task: asyncio.Task | None) -> bool:
    return task is not None and not task.done()


@dataclass
class CollectorRuntime:
    poll_task: asyncio.Task | None = None
    opcua_task: asyncio.Task | None = None
    monitor_task: asyncio.Task | None = None
    opcua_running: bool = False

    def is_running(self) -> bool:
        return _task_running(self.poll_task) or _task_running(self.monitor_task)

    def status(self) -> dict[str, Any]:
        return {
            "configured": settings.RUN_COLLECTOR,
            "running": self.is_running(),
            "poller_running": _task_running(self.poll_task),
            "opcua_running": self.opcua_running,
            "monitor_running": _task_running(self.monitor_task),
        }

    async def start(self) -> dict[str, Any]:
        if self.is_running():
            return self.status()

        self.poll_task = asyncio.create_task(poll_loop())
        logger.info("S7 poller baslatildi (coklu PLC, lazy connect)")

        async def _start_opcua() -> None:
            try:
                await opcua_server.start()
                self.opcua_running = True
                logger.info("OPC UA server baslatildi")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.opcua_running = False
                logger.warning("OPC UA server baslatilamadi: %s", e)

        self.opcua_task = asyncio.create_task(_start_opcua())

        from app.monitor.monitor import plc_monitor_loop

        self.monitor_task = asyncio.create_task(plc_monitor_loop())
        logger.info("PLC monitor baslatildi")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        tasks = [task for task in (self.monitor_task, self.opcua_task, self.poll_task) if task]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.opcua_running or self.opcua_task is not None:
            await opcua_server.stop()
        await plc_manager.disconnect_all()
        self.poll_task = None
        self.opcua_task = None
        self.monitor_task = None
        self.opcua_running = False
        return self.status()


collector_runtime = CollectorRuntime()


async def start_collector() -> dict[str, Any]:
    return await collector_runtime.start()


async def stop_collector() -> dict[str, Any]:
    return await collector_runtime.stop()


async def start_runtime_scheduler() -> dict[str, Any]:
    sched = get_scheduler()
    if sched is None or not getattr(sched, "running", False):
        await start_scheduler(settings.DATABASE_URL)
    return scheduler_status()


def stop_runtime_scheduler() -> dict[str, Any]:
    stop_scheduler()
    return scheduler_status()


def scheduler_status() -> dict[str, Any]:
    sched = get_scheduler()
    return {
        "configured": settings.RUN_SCHEDULER,
        "running": sched is not None and getattr(sched, "running", False),
    }


def runtime_status() -> dict[str, Any]:
    return {
        "controls_enabled": True,
        "backend": {
            "status": "ok",
            "uptime_seconds": metrics.uptime_seconds(),
            "started_at": metrics.process_started_at().isoformat(),
        },
        "collector": collector_runtime.status(),
        "scheduler": scheduler_status(),
    }
