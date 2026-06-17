"""Bellek içi halka tampon log handler'ı — canlı log akışı için.

Her log kaydını sınırlı bir deque'e (varsayılan 500) monoton bir ``seq``
ile yazar. Metrics sayfasındaki canlı konsol bu tamponu SSE ile tail eder.
Poller ve s7_collector zaten ``logging`` üzerinden yazdığından ek kod
gerektirmez; handler root logger'a bağlanır (main.py).
"""

import logging
import threading
from collections import deque
from datetime import UTC, datetime


class RingLogHandler(logging.Handler):
    """Log kayıtlarını sınırlı bir halka tampona yazan thread-safe handler."""

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self._buf: deque[dict] = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            try:
                msg = record.getMessage()
            except Exception:
                msg = record.msg  # fallback to raw message if formatting fails
            ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
            with self._lock:
                self._seq += 1
                self._buf.append(
                    {
                        "seq": self._seq,
                        "ts": ts,
                        "level": record.levelname,
                        "levelno": record.levelno,
                        "name": record.name,
                        "msg": msg,
                    }
                )
        except Exception:  # logging handler sözleşmesi: asla yükseltme
            self.handleError(record)

    def snapshot(self, after_seq: int = 0, min_level: int = logging.INFO) -> list[dict]:
        with self._lock:
            items = list(self._buf)
        return [r for r in items if r["seq"] > after_seq and r["levelno"] >= min_level]


log_buffer = RingLogHandler(maxlen=500)
