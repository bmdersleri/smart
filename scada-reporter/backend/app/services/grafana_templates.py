from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

TemplateKey = Literal["facility_overview", "water_quality"]


@dataclass(frozen=True)
class GrafanaDashboardTemplate:
    key: TemplateKey
    name: str
    description: str
    requires_tags: bool


TEMPLATES: tuple[GrafanaDashboardTemplate, ...] = (
    GrafanaDashboardTemplate(
        key="facility_overview",
        name="Tesis Genel Durum",
        description="Tag sayısı, veri tazeliği, okuma hacmi ve BAD kalite oranı.",
        requires_tags=False,
    ),
    GrafanaDashboardTemplate(
        key="water_quality",
        name="Su Kalitesi",
        description="Seçilen pH, klor, bulanıklık, sıcaklık gibi tag trendleri.",
        requires_tags=True,
    ),
)


def list_templates() -> list[dict]:
    return [
        {
            "key": t.key,
            "name": t.name,
            "description": t.description,
            "requires_tags": t.requires_tags,
        }
        for t in TEMPLATES
    ]


def get_template(key: str) -> GrafanaDashboardTemplate:
    for template in TEMPLATES:
        if template.key == key:
            return template
    raise ValueError(f"Bilinmeyen Grafana şablonu: {key}")


def dashboard_uid(template: str, owner_id: int, title: str, tag_ids: list[int]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:14] or "dashboard"
    digest_src = f"{template}:{owner_id}:{title}:{','.join(map(str, sorted(tag_ids)))}"
    digest = hashlib.sha1(digest_src.encode("utf-8")).hexdigest()[:8]
    return f"sr-{template[:3]}-{owner_id}-{slug}-{digest}"[:40]


def _tag_filter(tag_ids: list[int]) -> str:
    safe_ids = [int(tag_id) for tag_id in tag_ids]
    if not safe_ids:
        raise ValueError("Bu şablon için en az bir tag seçilmeli")
    return ", ".join(str(tag_id) for tag_id in sorted(set(safe_ids)))


def _timeseries_panel(
    panel_id: int,
    title: str,
    raw_sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    unit: str = "short",
) -> dict:
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": {"type": "postgres", "uid": "timescaledb"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 1,
                    "fillOpacity": 8,
                    "showPoints": "never",
                    "spanNulls": True,
                },
                "color": {"mode": "palette-classic"},
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "right",
                "calcs": ["last", "min", "max"],
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [{"refId": "A", "format": "time_series", "rawSql": raw_sql}],
    }


def _stat_panel(panel_id: int, title: str, raw_sql: str, *, x: int, y: int, w: int, h: int) -> dict:
    return {
        "id": panel_id,
        "type": "stat",
        "title": title,
        "datasource": {"type": "postgres", "uid": "timescaledb"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "auto",
        },
        "targets": [{"refId": "A", "format": "table", "rawSql": raw_sql}],
    }


def _table_panel(
    panel_id: int,
    title: str,
    raw_sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
) -> dict:
    return {
        "id": panel_id,
        "type": "table",
        "title": title,
        "datasource": {"type": "postgres", "uid": "timescaledb"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"refId": "A", "format": "table", "rawSql": raw_sql}],
        "options": {"showHeader": True},
    }


def _base_dashboard(uid: str, title: str, tags: list[str], panels: list[dict]) -> dict:
    return {
        "id": None,
        "uid": uid,
        "title": title,
        "tags": ["scada", "generated", *tags],
        "timezone": "browser",
        "schemaVersion": 39,
        "refresh": "30s",
        "time": {"from": "now-24h", "to": "now"},
        "panels": panels,
    }


def build_facility_overview_dashboard(uid: str, title: str) -> dict:
    return _base_dashboard(
        uid,
        title,
        ["facility-overview"],
        [
            _stat_panel(1, "Toplam Tag", 'SELECT count(*) AS "Tag" FROM tags', x=0, y=0, w=6, h=5),
            _stat_panel(
                2,
                "Son Okuma",
                'SELECT EXTRACT(EPOCH FROM max(timestamp)) * 1000 AS "Son Okuma" FROM tag_readings',
                x=6,
                y=0,
                w=6,
                h=5,
            ),
            _stat_panel(
                3,
                "Son 24s Okuma",
                (
                    'SELECT count(*) AS "Okuma" FROM tag_readings '
                    "WHERE timestamp >= now() - INTERVAL '24 hours'"
                ),
                x=12,
                y=0,
                w=6,
                h=5,
            ),
            _stat_panel(
                4,
                "BAD Kalite %",
                (
                    "SELECT 100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
                    '/ NULLIF(count(*), 0) AS "BAD %" FROM tag_readings '
                    "WHERE timestamp >= now() - INTERVAL '24 hours'"
                ),
                x=18,
                y=0,
                w=6,
                h=5,
            ),
            _timeseries_panel(
                5,
                "Okuma Hacmi",
                (
                    "SELECT $__timeGroupAlias(timestamp, '5m'), count(*) AS \"Okuma\" "
                    "FROM tag_readings WHERE $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1"
                ),
                x=0,
                y=5,
                w=12,
                h=8,
            ),
            _timeseries_panel(
                6,
                "BAD Kalite Oranı",
                (
                    "SELECT $__timeGroupAlias(timestamp, '15m'), "
                    "100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
                    '/ NULLIF(count(*), 0) AS "BAD %" FROM tag_readings '
                    "WHERE $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1"
                ),
                x=12,
                y=5,
                w=12,
                h=8,
                unit="percent",
            ),
            _table_panel(
                7,
                "Son Değerler",
                (
                    "SELECT DISTINCT ON (t.id) t.name, t.device, tr.value, "
                    "t.unit, tr.quality, tr.timestamp "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    "ORDER BY t.id, tr.timestamp DESC LIMIT 20"
                ),
                x=0,
                y=13,
                w=24,
                h=8,
            ),
        ],
    )


def build_water_quality_dashboard(uid: str, title: str, tag_ids: list[int]) -> dict:
    ids = _tag_filter(tag_ids)
    return _base_dashboard(
        uid,
        title,
        ["water-quality"],
        [
            _timeseries_panel(
                1,
                "Su Kalitesi Trendleri",
                (
                    "SELECT $__time(tr.timestamp) AS time, t.name AS metric, tr.value AS value "
                    "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
                    f"WHERE $__timeFilter(tr.timestamp) AND tr.tag_id IN ({ids}) ORDER BY 1"
                ),
                x=0,
                y=0,
                w=24,
                h=11,
            ),
            _table_panel(
                2,
                "Son Değerler",
                (
                    "SELECT DISTINCT ON (t.id) t.name, tr.value, t.unit, tr.quality, tr.timestamp "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE t.id IN ({ids}) ORDER BY t.id, tr.timestamp DESC"
                ),
                x=0,
                y=11,
                w=12,
                h=8,
            ),
            _table_panel(
                3,
                "Limit Aşımı Özeti",
                (
                    "SELECT t.name, "
                    "sum(CASE WHEN t.min_alarm IS NOT NULL "
                    "AND tr.value < t.min_alarm THEN 1 ELSE 0 END) "
                    'AS "Alt Limit", '
                    "sum(CASE WHEN t.max_alarm IS NOT NULL "
                    "AND tr.value > t.max_alarm THEN 1 ELSE 0 END) "
                    'AS "Üst Limit" '
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE $__timeFilter(tr.timestamp) AND t.id IN ({ids}) "
                    "GROUP BY t.name ORDER BY t.name"
                ),
                x=12,
                y=11,
                w=12,
                h=8,
            ),
        ],
    )


_LAB_CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _lab_sql_code(value: str) -> str:
    """Return *value* as a safe single-quoted SQL literal.

    Codes come from the lab catalog, where operators can add entries, so they
    are validated against a strict allowlist (letters, digits, '_' and '-').
    The allowlist forbids quotes, so no SQL injection is possible.
    """
    if not _LAB_CODE_RE.match(value or ""):
        raise ValueError(f"Geçersiz kod (yalnız harf/rakam/_/- izinli): {value!r}")
    return f"'{value}'"


@dataclass
class LabParamSpec:
    id: int
    code: str
    name: str
    unit: str
    min_limit: float | None
    max_limit: float | None


def lab_dashboard_uid(point_id: int, parameter_ids: list[int]) -> str:
    ids = ",".join(str(i) for i in sorted({int(i) for i in parameter_ids}))
    digest = hashlib.sha1(ids.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"sr-lab-{int(point_id)}-{digest}"


def _lab_timeseries_panel(panel_id: int, point_code: str, param: LabParamSpec, *, y: int) -> dict:
    """A v_lab_timeseries time-series panel for one parameter, with min/max limit lines."""
    raw_sql = (
        f'SELECT time AS "time", param_code AS metric, value '
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code = {_lab_sql_code(param.code)} "
        f"AND $__timeFilter(time) ORDER BY time"
    )
    title = f"{param.name}{f' ({param.unit})' if param.unit else ''}"
    panel = _timeseries_panel(
        panel_id, title, raw_sql, x=0, y=y, w=24, h=8, unit=param.unit or "short"
    )
    steps: list[dict] = [{"color": "green", "value": None}]
    if param.min_limit is not None:
        steps.append({"color": "orange", "value": param.min_limit})
    if param.max_limit is not None:
        steps.append({"color": "red", "value": param.max_limit})
    # Grafana wants steps sorted ascending; the base None step stays first.
    steps[1:] = sorted(steps[1:], key=lambda s: s["value"])
    panel["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": steps}
    panel["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] = {"mode": "line"}
    return panel


def build_lab_dashboard(
    *, point_id: int, point_code: str, point_name: str, params: list[LabParamSpec]
) -> dict:
    if not params:
        raise ValueError("Dashboard için en az bir parametre seçilmeli")
    panels: list[dict] = []
    y = 0
    for idx, param in enumerate(params, start=1):
        panels.append(_lab_timeseries_panel(idx, point_code, param, y=y))
        y += 8
    # latest-values table across the whole selection
    codes_in = ", ".join(_lab_sql_code(p.code) for p in params)
    table_sql = (
        f"SELECT time, param_name, value, unit, min_limit, max_limit "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code IN ({codes_in}) "
        f"AND $__timeFilter(time) ORDER BY time DESC LIMIT 200"
    )
    panels.append(_table_panel(len(params) + 1, "Son değerler", table_sql, x=0, y=y, w=24, h=10))
    uid = lab_dashboard_uid(point_id, [p.id for p in params])
    dash = _base_dashboard(uid, f"Lab — {point_name}", ["lab"], panels)
    dash["time"] = {"from": "now-30d", "to": "now"}
    return dash


def build_dashboard(template: str, uid: str, title: str, tag_ids: list[int] | None = None) -> dict:
    selected = tag_ids or []
    if template == "facility_overview":
        return build_facility_overview_dashboard(uid, title)
    if template == "water_quality":
        return build_water_quality_dashboard(uid, title, selected)
    raise ValueError(f"Bilinmeyen Grafana şablonu: {template}")


def report_dashboard_uid(template_id: int) -> str:
    return f"sr-rpt-{int(template_id)}"


def resolve_dashboard_time(time_range_type: str, custom_start, custom_end) -> dict:
    presets = {
        "last_1h": "now-1h",
        "last_24h": "now-24h",
        "last_7d": "now-7d",
        "last_30d": "now-30d",
    }
    if time_range_type == "custom" and custom_start and custom_end:
        return {"from": custom_start.isoformat(), "to": custom_end.isoformat()}
    return {"from": presets.get(time_range_type, "now-24h"), "to": "now"}


def build_report_template_dashboard(
    *,
    template_id: int,
    title: str,
    tag_ids: list[int],
    time_range_type: str,
    custom_start=None,
    custom_end=None,
    show_trend_charts: bool,
    show_summary_stats: bool,
    anomaly_enabled: bool,
    show_anomaly_table: bool,
) -> dict:
    ids = _tag_filter(tag_ids)  # int-coerce + validate non-empty
    panels: list[dict] = []
    pid = 1
    y = 0

    # Trend timeseries — included if requested OR as the non-empty fallback.
    want_trend = show_trend_charts or not (
        show_summary_stats or (anomaly_enabled and show_anomaly_table)
    )
    if want_trend:
        panels.append(
            _timeseries_panel(
                pid,
                "Tag Trendleri",
                (
                    "SELECT $__time(tr.timestamp) AS time, t.name AS metric, tr.value AS value "
                    "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
                    f"WHERE $__timeFilter(tr.timestamp) AND tr.tag_id IN ({ids}) ORDER BY 1"
                ),
                x=0,
                y=y,
                w=24,
                h=11,
            )
        )
        pid += 1
        y += 11

    if show_summary_stats:
        panels.append(
            _table_panel(
                pid,
                "Son Değerler",
                (
                    "SELECT DISTINCT ON (t.id) t.name, tr.value, t.unit, tr.quality, tr.timestamp "
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE t.id IN ({ids}) ORDER BY t.id, tr.timestamp DESC"
                ),
                x=0,
                y=y,
                w=12,
                h=8,
            )
        )
        pid += 1

    if anomaly_enabled and show_anomaly_table:
        panels.append(
            _table_panel(
                pid,
                "Limit Aşımı Özeti",
                (
                    "SELECT t.name, "
                    "sum(CASE WHEN t.min_alarm IS NOT NULL "
                    'AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS "Alt Limit", '
                    "sum(CASE WHEN t.max_alarm IS NOT NULL "
                    'AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS "Üst Limit" '
                    "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
                    f"WHERE $__timeFilter(tr.timestamp) AND t.id IN ({ids}) "
                    "GROUP BY t.name ORDER BY t.name"
                ),
                x=12,
                y=y,
                w=12,
                h=8,
            )
        )
        pid += 1

    dash = _base_dashboard(report_dashboard_uid(template_id), title, ["report-template"], panels)
    dash["time"] = resolve_dashboard_time(time_range_type, custom_start, custom_end)
    return dash
