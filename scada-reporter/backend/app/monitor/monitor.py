# app/monitor/monitor.py
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.plc_health_tracker import health_tracker
from app.collector.s7_collector import plc_manager
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.plc_health import PlcHealth
from app.models.plc_incident import PlcIncident
from app.monitor import notifier
from app.monitor.detector import (
    DetectorConfig,
    EvalResult,
    PlcMonitorState,
    PlcObservation,
    evaluate,
)
from app.monitor.notifier import AlertPayload

logger = logging.getLogger(__name__)

_MESSAGES = {
    "disconnected": "PLC bağlantısı koptu",
    "stale_data": "Bağlı ama veri akmıyor (bayat)",
    "partial_bad": "Bazı tag'ler sürekli hatalı (kısmi)",
    "flapping": "PLC sürekli bağlanıp kopuyor",
}


def _cfg() -> DetectorConfig:
    return DetectorConfig(
        stale_seconds=settings.PLC_STALE_SECONDS,
        partial_bad_ratio=settings.PLC_PARTIAL_BAD_RATIO,
        partial_bad_cycles=settings.PLC_PARTIAL_BAD_CYCLES,
        flap_count=settings.PLC_FLAP_COUNT,
        recover_cycles=settings.PLC_RECOVER_CYCLES,
    )


def _message(kind: str) -> str:
    return _MESSAGES.get(kind, kind)


async def apply_result(
    obs: PlcObservation,
    result: EvalResult,
    sessionmaker: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    ip, rack, slot = obs.key
    now_dt = datetime.now(UTC)
    payloads: list[AlertPayload] = []

    async with sessionmaker() as db:
        # açılan incident'lar
        for inc in result.opened:
            db.add(
                PlcIncident(
                    plc_ip=ip,
                    plc_name=obs.name,
                    rack=rack,
                    slot=slot,
                    kind=inc.kind,
                    severity=inc.severity,
                    message=_message(inc.kind),
                    detail=inc.detail,
                    opened_at=now_dt,
                    notified=True,
                )
            )
            payloads.append(
                AlertPayload(
                    ip, obs.name, inc.kind, inc.severity, _message(inc.kind), "opened", inc.detail
                )
            )

        # çözülen incident'lar
        for kind in result.resolved:
            rows = (
                (
                    await db.execute(
                        select(PlcIncident).where(
                            PlcIncident.plc_ip == ip,
                            PlcIncident.rack == rack,
                            PlcIncident.slot == slot,
                            PlcIncident.kind == kind,
                            PlcIncident.resolved_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if rows:
                for row in rows:
                    row.resolved_at = now_dt
                sev = rows[0].severity
                payloads.append(
                    AlertPayload(ip, obs.name, kind, sev, _message(kind), "resolved", {})
                )

        # plc_health upsert
        health = (
            await db.execute(
                select(PlcHealth).where(
                    PlcHealth.plc_ip == ip, PlcHealth.rack == rack, PlcHealth.slot == slot
                )
            )
        ).scalar_one_or_none()
        if health is None:
            health = PlcHealth(plc_ip=ip, rack=rack, slot=slot)
            db.add(health)
        health.plc_name = obs.name
        health.connected = obs.connected
        health.good_last_cycle = obs.good_count
        health.bad_last_cycle = obs.bad_count
        health.reconnects_last_min = obs.reconnects_in_window
        health.consecutive_fail = result.state.disconnected_streak
        health.open_incident_count = len(result.state.open)
        health.updated_at = now_dt
        if obs.good_count > 0:
            health.last_success_at = now_dt

        await db.commit()

    # bildirim (DB commit'ten sonra, döngüyü kırmadan)
    for p in payloads:
        try:
            await notifier.dispatch(p)
        except Exception as e:  # defansif — dispatch zaten yutar
            logger.warning("Uyarı gönderilemedi: %s", e)


async def plc_monitor_loop() -> None:
    """Periyodik PLC sağlık değerlendirme döngüsü."""
    logger.info("PLC monitor basladi (periyot: %ds)", settings.PLC_MONITOR_INTERVAL)
    cfg = _cfg()
    states: dict[tuple[str, int, int], PlcMonitorState] = {}
    while True:
        try:
            now = time.monotonic()
            status = plc_manager.status()  # {ip: connected}
            for key in health_tracker.known_keys():
                health_tracker.observe_connection(key, "", status.get(key[0], False), now)
            for obs in health_tracker.snapshot(now, settings.PLC_FLAP_WINDOW_SECONDS):
                prev = states.get(obs.key, PlcMonitorState())
                result = evaluate(prev, obs, cfg, now)
                states[obs.key] = result.state
                await apply_result(obs, result)
        except Exception as e:
            logger.error("PLC monitor hatasi: %s", e)
        await asyncio.sleep(settings.PLC_MONITOR_INTERVAL)
