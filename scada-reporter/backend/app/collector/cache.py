"""Son-değer (latest value) önbelleği.

Poller her tick sonrası buraya yazar; OPC UA server 'son değer' sorgularını
DB'deki pahalı GROUP BY MAX(timestamp) yerine buradan okur. Tek-process içi;
çok-process dağıtımında aynı arayüz ardında Redis ile değiştirilebilir.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CachedReading:
    value: float | None
    quality: int
    timestamp: datetime


class LatestValueCache:
    """tag_id -> son CachedReading. Thread-safe (poller thread'leri + asyncio loop)."""

    def __init__(self) -> None:
        self._data: dict[int, CachedReading] = {}
        self._lock = threading.Lock()

    def update(self, tag_id: int, value: float | None, quality: int, timestamp: datetime) -> None:
        with self._lock:
            self._data[tag_id] = CachedReading(value, quality, timestamp)

    def update_many(self, items: list[tuple[int, float | None, int]], timestamp: datetime) -> None:
        with self._lock:
            for tag_id, value, quality in items:
                self._data[tag_id] = CachedReading(value, quality, timestamp)

    def get(self, tag_id: int) -> CachedReading | None:
        with self._lock:
            return self._data.get(tag_id)

    def get_many(self, tag_ids: list[int]) -> dict[int, CachedReading]:
        with self._lock:
            return {tid: self._data[tid] for tid in tag_ids if tid in self._data}

    def snapshot(self) -> dict[int, CachedReading]:
        with self._lock:
            return dict(self._data)


latest_cache = LatestValueCache()
