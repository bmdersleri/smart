"""Prometheus metrikleri — poller/PLC okuma sağlığı + HTTP + DB pool.

Toplama döngüsünü ayarlamak için gereken sinyaller: tick süresi, PLC başına
okuma gecikmesi, yazılan satır sayısı, BAD-kalite oranı. /metrics endpoint'i
``render()`` çıktısını Prometheus text formatında sunar.

HTTP istek sayacı ve gecikme histogramı Starlette middleware tarafından doldurulur
(bkz. app/main.py). DB pool gauge'ları render() çağrısında güncellenir.
"""

import time
from datetime import UTC, datetime

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Process start (wall-clock epoch), recorded once at import.
_PROCESS_START = time.time()

tick_duration = Histogram(
    "scada_tick_duration_seconds",
    "Poller tek tick süresi (saniye)",
)
plc_read_duration = Histogram(
    "scada_plc_read_seconds",
    "PLC başına batch okuma süresi (saniye)",
    ["plc"],
)
rows_written = Counter(
    "scada_rows_written_total",
    "DB'ye yazılan toplam okuma satırı",
)
bad_quality = Counter(
    "scada_bad_quality_total",
    "BAD-kalite okuma sayısı",
)

# ── HTTP metrics (populated by middleware in main.py) ──────────────────────
http_requests_total = Counter(
    "scada_http_requests_total",
    "Toplam HTTP istek sayısı",
    ["method", "status"],
)
http_request_duration = Histogram(
    "scada_http_request_seconds",
    "HTTP istek süresi (saniye)",
    ["method"],
)

# ── DB pool gauges (updated at scrape time in render()) ───────────────────
db_pool_size = Gauge(
    "scada_db_pool_size",
    "DB bağlantı havuzu kapasitesi",
)
db_pool_checked_out = Gauge(
    "scada_db_pool_checked_out",
    "Şu an kullanımda olan DB bağlantısı",
)

# ── Process uptime ────────────────────────────────────────────────────────
process_start_time_seconds = Gauge(
    "scada_process_start_time_seconds",
    "Backend process başlangıç zamanı (Unix epoch saniye)",
)
process_start_time_seconds.set(_PROCESS_START)

CONTENT_TYPE = CONTENT_TYPE_LATEST


def uptime_seconds() -> float:
    """Process başlangıcından bu yana geçen saniye."""
    return time.time() - _PROCESS_START


def process_started_at() -> datetime:
    """Process başlangıç zamanı (tz-aware UTC)."""
    return datetime.fromtimestamp(_PROCESS_START, UTC)


def observe_tick(duration_s: float) -> None:
    tick_duration.observe(duration_s)


def observe_plc_read(plc: str, duration_s: float) -> None:
    plc_read_duration.labels(plc=plc).observe(duration_s)


def add_rows_written(n: int) -> None:
    if n:
        rows_written.inc(n)


def add_bad_quality(n: int) -> None:
    if n:
        bad_quality.inc(n)


def _update_pool_gauges() -> None:
    """Scrape-time pool stat update.

    engine.pool is a StaticPool in tests (no .size()/.checkedout()) — guard
    every attribute access so tests don't crash.
    """
    try:
        from app.core.database import engine  # local import to avoid circular

        pool = engine.pool
        size = getattr(pool, "size", None)
        checked = getattr(pool, "checkedout", None)
        if callable(size):
            db_pool_size.set(size())
        if callable(checked):
            db_pool_checked_out.set(checked())
    except Exception:
        pass  # never crash the /metrics endpoint due to pool probe


def render() -> bytes:
    _update_pool_gauges()
    return generate_latest()


def _val(name: str, labels: dict | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def summary() -> dict:
    """Dashboard canlı izleme için metrik özeti (JSON).

    Prometheus registry'den okur: yazılan/BAD satır sayaçları, tick ortalama
    süresi, PLC başına ortalama okuma gecikmesi.
    """
    rows = _val("scada_rows_written_total")
    bad = _val("scada_bad_quality_total")
    tick_count = _val("scada_tick_duration_seconds_count")
    tick_sum = _val("scada_tick_duration_seconds_sum")
    total_reads = rows + bad

    plcs: dict[str, dict[str, float]] = {}
    for metric in plc_read_duration.collect():
        for s in metric.samples:
            if s.name.endswith("_count"):
                plcs.setdefault(s.labels["plc"], {})["count"] = s.value
            elif s.name.endswith("_sum"):
                plcs.setdefault(s.labels["plc"], {})["sum"] = s.value
    plc_list = [
        {
            "plc": ip,
            "count": d.get("count", 0.0),
            "avg_seconds": (d["sum"] / d["count"]) if d.get("count") else None,
        }
        for ip, d in sorted(plcs.items())
    ]

    return {
        "rows_written_total": rows,
        "bad_quality_total": bad,
        "bad_ratio": (bad / total_reads) if total_reads else None,
        "tick_count": tick_count,
        "tick_avg_seconds": (tick_sum / tick_count) if tick_count else None,
        "plcs": plc_list,
    }
