"""Canlı son-değer akışı (Server-Sent Events).

Poller her tick latest_cache'i günceller; bu endpoint cache'i periyodik olarak
SSE frame'leri halinde push eder. Böylece dashboard 5sn'lik REST polling yerine
gerçek-zamanlı güncellenir. EventSource başlık gönderemediği için kimlik
doğrulama query-param token ile yapılır.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import authenticate_token
from app.collector.cache import CachedReading, latest_cache
from app.core.config import settings
from app.core.database import get_db
from app.core.log_buffer import log_buffer

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _format_frame(items: dict[int, CachedReading]) -> str:
    payload = {
        str(tid): {"v": cr.value, "q": cr.quality, "t": cr.timestamp.isoformat()}
        for tid, cr in items.items()
    }
    return f"data: {json.dumps(payload)}\n\n"


async def latest_event_stream(
    tag_ids: list[int],
    interval: float = 2.0,
    *,
    max_events: int | None = None,
) -> AsyncGenerator[str, None]:
    """Belirtilen tag'lerin (boşsa tümünün) son değerlerini SSE frame'i olarak akıt."""
    sent = 0
    while max_events is None or sent < max_events:
        snap = latest_cache.snapshot()
        items = {t: snap[t] for t in tag_ids if t in snap} if tag_ids else snap
        yield _format_frame(items)
        sent += 1
        if max_events is not None and sent >= max_events:
            break
        await asyncio.sleep(interval)


@router.get("/stream")
async def stream(
    token: str = Query(...),
    tag_ids: list[int] = Query(default=[]),
    limit: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    await authenticate_token(token, db)
    interval = settings.OPCUA_SERVER_UPDATE_INTERVAL or 2
    return StreamingResponse(
        latest_event_stream(tag_ids, interval, max_events=limit),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def log_event_stream(
    after: int = 0,
    min_level: int = logging.INFO,
    interval: float = 1.0,
    *,
    max_events: int | None = None,
) -> AsyncGenerator[str, None]:
    """Halka tampondaki yeni log kayıtlarını SSE frame'i (JSON dizisi) olarak akıt."""
    last = after
    sent = 0
    while max_events is None or sent < max_events:
        recs = log_buffer.snapshot(after_seq=last, min_level=min_level)
        if recs:
            last = recs[-1]["seq"]
            yield f"data: {json.dumps(recs)}\n\n"
            sent += 1
            if max_events is not None and sent >= max_events:
                break
        await asyncio.sleep(interval)


@router.get("/logs/stream")
async def logs_stream(
    token: str = Query(...),
    after: int = Query(default=0, ge=0),
    level: str = Query(default="INFO"),
    limit: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    await authenticate_token(token, db)
    min_level = logging.getLevelName(level.upper())
    if not isinstance(min_level, int):
        min_level = logging.INFO
    return StreamingResponse(
        log_event_stream(after, min_level, max_events=limit),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
