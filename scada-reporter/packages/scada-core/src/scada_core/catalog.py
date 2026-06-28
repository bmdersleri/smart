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
    tier: str = "read"  # "read" | "write" | "destructive"


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
    Capability(
        "update_tag",
        "Bir tag'in alanlarını güncelle (unit/device/channel/alarm).",
        _obj(
            {
                "tag_id": {"type": "integer"},
                "unit": {"type": "string"},
                "device": {"type": "string"},
                "channel": {"type": "string"},
                "description": {"type": "string"},
                "min_alarm": {"type": "number"},
                "max_alarm": {"type": "number"},
            },
            ["tag_id"],
        ),
        lambda c, a: c.update_tag(
            a["tag_id"],
            a.get("unit"),
            a.get("device"),
            a.get("channel"),
            a.get("description"),
            a.get("min_alarm"),
            a.get("max_alarm"),
        ),
        tier="write",
    ),
    Capability(
        "delete_tag",
        "Bir tag'i kalıcı olarak sil.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.delete_tag(a["tag_id"]),
        tier="destructive",
    ),
    Capability(
        "watchlist_add",
        "Bir tag'i izleme listesine ekle.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.watchlist_add(a["tag_id"]),
        tier="write",
    ),
    Capability(
        "watchlist_remove",
        "Bir tag'i izleme listesinden çıkar.",
        _obj({"tag_id": {"type": "integer"}}, ["tag_id"]),
        lambda c, a: c.watchlist_remove(a["tag_id"]),
        tier="write",
    ),
    Capability(
        "annotation_add",
        "Bir zaman damgasına (opsiyonel tag'e) not ekle.",
        _obj(
            {"ts": {"type": "string"}, "text": {"type": "string"}, "tag_id": {"type": "integer"}},
            ["ts", "text"],
        ),
        lambda c, a: c.annotation_add(a["ts"], a["text"], a.get("tag_id")),
        tier="write",
    ),
    Capability(
        "annotation_delete",
        "Bir annotation'ı sil.",
        _obj({"annotation_id": {"type": "integer"}}, ["annotation_id"]),
        lambda c, a: c.annotation_delete(a["annotation_id"]),
        tier="write",
    ),
    Capability(
        "template_create",
        "Rapor şablonu oluştur (name + tag_ids zorunlu).",
        _obj({"payload": {"type": "object"}}, ["payload"]),
        lambda c, a: c.template_create(a["payload"]),
        tier="write",
    ),
    Capability(
        "template_update",
        "Rapor şablonunu güncelle.",
        _obj(
            {"template_id": {"type": "integer"}, "payload": {"type": "object"}},
            ["template_id", "payload"],
        ),
        lambda c, a: c.template_update(a["template_id"], a["payload"]),
        tier="write",
    ),
    Capability(
        "template_run",
        "Rapor şablonunu çalıştır (opsiyonel start/end).",
        _obj(
            {
                "template_id": {"type": "integer"},
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            ["template_id"],
        ),
        lambda c, a: c.template_run(a["template_id"], a.get("start"), a.get("end")),
        tier="write",
    ),
    Capability(
        "template_delete",
        "Rapor şablonunu sil.",
        _obj({"template_id": {"type": "integer"}}, ["template_id"]),
        lambda c, a: c.template_delete(a["template_id"]),
        tier="destructive",
    ),
    Capability(
        "scheduled_create",
        "Zamanlanmış rapor oluştur.",
        _obj({"payload": {"type": "object"}}, ["payload"]),
        lambda c, a: c.scheduled_create(a["payload"]),
        tier="write",
    ),
    Capability(
        "scheduled_update",
        "Zamanlanmış raporu güncelle.",
        _obj(
            {"scheduled_id": {"type": "integer"}, "payload": {"type": "object"}},
            ["scheduled_id", "payload"],
        ),
        lambda c, a: c.scheduled_update(a["scheduled_id"], a["payload"]),
        tier="write",
    ),
    Capability(
        "scheduled_toggle",
        "Zamanlanmış raporu etkinleştir/devre dışı bırak.",
        _obj({"scheduled_id": {"type": "integer"}}, ["scheduled_id"]),
        lambda c, a: c.scheduled_toggle(a["scheduled_id"]),
        tier="write",
    ),
    Capability(
        "scheduled_delete",
        "Zamanlanmış raporu sil.",
        _obj({"scheduled_id": {"type": "integer"}}, ["scheduled_id"]),
        lambda c, a: c.scheduled_delete(a["scheduled_id"]),
        tier="destructive",
    ),
    Capability(
        "archive_delete",
        "Bir arşiv kaydını sil.",
        _obj({"archive_id": {"type": "integer"}}, ["archive_id"]),
        lambda c, a: c.archive_delete(a["archive_id"]),
        tier="destructive",
    ),
    Capability(
        "group_create",
        "Tag grubu oluştur.",
        _obj(
            {
                "name": {"type": "string"},
                "parent_id": {"type": "integer"},
                "sort_order": {"type": "integer"},
            },
            ["name"],
        ),
        lambda c, a: c.group_create(a["name"], a.get("parent_id"), a.get("sort_order", 0)),
        tier="write",
    ),
    Capability(
        "group_update",
        "Tag grubunu güncelle.",
        _obj(
            {
                "group_id": {"type": "integer"},
                "name": {"type": "string"},
                "parent_id": {"type": "integer"},
                "sort_order": {"type": "integer"},
            },
            ["group_id"],
        ),
        lambda c, a: c.group_update(
            a["group_id"], a.get("name"), a.get("parent_id"), a.get("sort_order")
        ),
        tier="write",
    ),
    Capability(
        "group_assign",
        "Tag'leri bir gruba ata.",
        _obj(
            {
                "group_id": {"type": "integer"},
                "tag_ids": {"type": "array", "items": {"type": "integer"}},
            },
            ["group_id", "tag_ids"],
        ),
        lambda c, a: c.group_assign(a["group_id"], a["tag_ids"]),
        tier="write",
    ),
    Capability(
        "group_unassign",
        "Tag'lerin grup atamasını kaldır.",
        _obj({"tag_ids": {"type": "array", "items": {"type": "integer"}}}, ["tag_ids"]),
        lambda c, a: c.group_unassign(a["tag_ids"]),
        tier="write",
    ),
    Capability(
        "group_delete",
        "Tag grubunu sil.",
        _obj({"group_id": {"type": "integer"}}, ["group_id"]),
        lambda c, a: c.group_delete(a["group_id"]),
        tier="destructive",
    ),
    Capability(
        "plc_create",
        "PLC bağlantı yapılandırması oluştur.",
        _obj(
            {
                "name": {"type": "string"},
                "ip": {"type": "string"},
                "rack": {"type": "integer"},
                "slot": {"type": "integer"},
            },
            ["name"],
        ),
        lambda c, a: c.plc_create(a["name"], a.get("ip", ""), a.get("rack", 0), a.get("slot", 1)),
        tier="write",
    ),
    Capability(
        "plc_update",
        "PLC bağlantı yapılandırmasını güncelle.",
        _obj(
            {
                "name": {"type": "string"},
                "ip": {"type": "string"},
                "rack": {"type": "integer"},
                "slot": {"type": "integer"},
            },
            ["name", "ip"],
        ),
        lambda c, a: c.plc_update(a["name"], a["ip"], a.get("rack", 0), a.get("slot", 1)),
        tier="write",
    ),
    Capability(
        "plc_delete",
        "PLC yapılandırmasını sil.",
        _obj({"name": {"type": "string"}}, ["name"]),
        lambda c, a: c.plc_delete(a["name"]),
        tier="destructive",
    ),
    Capability(
        "user_create",
        "Kullanıcı oluştur (admin).",
        _obj(
            {
                "username": {"type": "string"},
                "email": {"type": "string"},
                "password": {"type": "string"},
                "full_name": {"type": "string"},
                "role": {"type": "string"},
            },
            ["username", "email", "password"],
        ),
        lambda c, a: c.user_create(
            a["username"],
            a["email"],
            a["password"],
            a.get("full_name", ""),
            a.get("role", "operator"),
            a.get("permission_overrides"),
        ),
        tier="destructive",
    ),
    Capability(
        "user_update",
        "Kullanıcıyı güncelle (admin).",
        _obj(
            {
                "user_id": {"type": "integer"},
                "email": {"type": "string"},
                "full_name": {"type": "string"},
                "role": {"type": "string"},
                "is_active": {"type": "boolean"},
            },
            ["user_id"],
        ),
        lambda c, a: c.user_update(
            a["user_id"],
            a.get("email"),
            a.get("full_name"),
            a.get("role"),
            a.get("is_active"),
            a.get("permission_overrides"),
        ),
        tier="destructive",
    ),
    Capability(
        "user_set_password",
        "Kullanıcı parolasını değiştir (admin).",
        _obj(
            {"user_id": {"type": "integer"}, "password": {"type": "string"}},
            ["user_id", "password"],
        ),
        lambda c, a: c.user_set_password(a["user_id"], a["password"]),
        tier="destructive",
    ),
    Capability(
        "user_delete",
        "Kullanıcıyı sil (admin).",
        _obj({"user_id": {"type": "integer"}}, ["user_id"]),
        lambda c, a: c.user_delete(a["user_id"]),
        tier="destructive",
    ),
    Capability(
        "compliance_overview",
        "Uyumluluk merkezi özeti: izinler, açık olay sayıları ve durum dağılımı.",
        _obj({}),
        lambda c, a: c.compliance_overview(),
        tier="read",
    ),
    Capability(
        "compliance_list_events",
        "Uyumluluk olaylarını listele (opsiyonel filtreler: izin, durum, "
        "başlangıç/bitiş zamanı). {total, items} döner.",
        _obj(
            {
                "permit_id": {"type": "integer"},
                "start": {"type": "string", "description": "ISO 8601 başlangıç"},
                "end": {"type": "string", "description": "ISO 8601 bitiş"},
                "status": {"type": "string"},
            }
        ),
        lambda c, a: c.compliance_events(
            a.get("permit_id"), a.get("start"), a.get("end"), a.get("status")
        ),
        tier="read",
    ),
    Capability(
        "compliance_evaluate",
        "Bir izin için verilen dönemde uyumluluk değerlendirmesini çalıştır "
        "(olayları oluşturur/günceller).",
        _obj(
            {
                "permit_id": {"type": "integer"},
                "start": {"type": "string", "description": "ISO 8601 başlangıç"},
                "end": {"type": "string", "description": "ISO 8601 bitiş"},
            },
            ["permit_id", "start", "end"],
        ),
        lambda c, a: c.compliance_evaluate(a["permit_id"], a["start"], a["end"]),
        tier="write",
    ),
]

CATALOG: dict[str, Capability] = {c.name: c for c in CAPABILITIES}
