"""Canlı son-değer akışı (Server-Sent Events).

Poller her tick latest_cache'i günceller; bu endpoint cache'i periyodik olarak
SSE frame'leri halinde push eder. Böylece dashboard 5sn'lik REST polling yerine
gerçek-zamanlı güncellenir. EventSource başlık gönderemediği için kimlik
doğrulama query-param token ile yapılır.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import authenticate_token
from app.collector.cache import CachedReading, latest_cache
from app.core.config import settings
from app.core.database import get_db

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
