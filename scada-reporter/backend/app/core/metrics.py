"""Prometheus metrikleri — poller/PLC okuma sağlığı.

Toplama döngüsünü ayarlamak için gereken sinyaller: tick süresi, PLC başına
okuma gecikmesi, yazılan satır sayısı, BAD-kalite oranı. /metrics endpoint'i
``render()`` çıktısını Prometheus text formatında sunar.
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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

CONTENT_TYPE = CONTENT_TYPE_LATEST


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


def render() -> bytes:
    return generate_latest()
