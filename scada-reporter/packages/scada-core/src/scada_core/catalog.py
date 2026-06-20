from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .client import AsyncScadaClient
from .envelope import Result

Handler = Callable[[AsyncScadaClient, dict], Awaitable[Result]]


@dataclass
class Capability:
    name: str
    description: str
    input_schema: dict
    handler: Handler
    read_only: bool = True


def _obj(props: dict, required: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


CAPABILITIES: list[Capability] = [
    Capability(
        "query_current_values",
        "Aktif tag'lerin (veya verilen alt kümenin) en güncel okumasını döner: "
        "ad, değer, birim, zaman damgası, kalite.",
        _obj(
            {
                "tag_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filtrelenecek tag adları (boşsa tümü)",
                }
            }
        ),
        lambda c, a: c.current_values(a.get("tag_names")),
    ),
    Capability(
        "query_trend",
        "Bir veya daha çok tag için bir zaman aralığında geçmiş trend verisi. "
        "Tag adları otomatik çözümlenir.",
        _obj(
            {
                "tags": {"type": "array", "items": {"type": "string"}},
                "start": {"type": "string", "description": "ISO 8601 başlangıç"},
                "end": {"type": "string", "description": "ISO 8601 bitiş"},
            },
            ["tags", "start", "end"],
        ),
        lambda c, a: c.query_trend(a["tags"], a["start"], a["end"]),
    ),
    Capability(
        "generate_report",
        "Veri raporu üret (excel/pdf/json/csv). Sonuç indirme URL'si döner.",
        _obj(
            {
                "tags": {"type": "array", "items": {"type": "string"}},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": ["excel", "pdf", "json", "csv"],
                    "default": "excel",
                },
                "aggregation": {
                    "type": "string",
                    "enum": ["raw", "hourly", "daily", "monthly"],
                    "default": "raw",
                },
            },
            ["tags", "start", "end"],
        ),
        lambda c, a: c.generate_report(
            a["tags"], a["start"], a["end"], a.get("format", "excel"), a.get("aggregation", "raw")
        ),
    ),
    Capability(
        "list_tags",
        "Tüm yapılandırılmış tag'leri meta veriyle listele: ad, birim, cihaz, PLC, "
        "aktiflik, deadband.",
        _obj({}),
        lambda c, a: c.list_tags(),
    ),
    Capability(
        "list_plcs",
        "Tüm yapılandırılmış PLC'leri bağlantı durumu, IP, rack, slot ile listele.",
        _obj({}),
        lambda c, a: c.list_plcs(),
    ),
    Capability(
        "run_sql_query",
        "Zaman serisi veritabanında salt-okunur SQL çalıştır. Sadece SELECT/WITH/EXPLAIN.",
        _obj({"query": {"type": "string", "description": "SQL (SELECT/WITH/EXPLAIN)"}}, ["query"]),
        lambda c, a: c.run_sql(a["query"]),
    ),
    Capability(
        "detect_anomalies",
        "Bir tag'in son verisinde z-score tabanlı anomali tespiti.",
        _obj(
            {
                "tag_name": {"type": "string"},
                "window": {"type": "string", "default": "7d"},
                "threshold": {"type": "number", "default": 3.0},
            },
            ["tag_name"],
        ),
        lambda c, a: c.detect_anomalies(
            a["tag_name"], a.get("window", "7d"), a.get("threshold", 3.0)
        ),
    ),
    Capability(
        "predict_trend",
        "Lineer regresyonla bir tag için gelecek değer tahmini.",
        _obj(
            {"tag_name": {"type": "string"}, "horizon": {"type": "string", "default": "24h"}},
            ["tag_name"],
        ),
        lambda c, a: c.predict_trend(a["tag_name"], a.get("horizon", "24h")),
    ),
    Capability(
        "get_system_health",
        "Genel sistem sağlığı: PLC bağlantısı, tag sayıları, DB durumu.",
        _obj({}),
        lambda c, a: c.system_health(),
    ),
    Capability(
        "resolve_tag",
        "Kısmi ada göre tag ara (fuzzy). Agent'ın tam tag adını bulması için.",
        _obj({"query": {"type": "string"}}, ["query"]),
        lambda c, a: c.resolve_tag(a["query"]),
    ),
]

CATALOG: dict[str, Capability] = {c.name: c for c in CAPABILITIES}
