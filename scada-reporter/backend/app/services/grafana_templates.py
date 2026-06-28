from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings

TemplateKey = Literal["facility_overview", "water_quality"]


@dataclass(frozen=True)
class GrafanaDashboardTemplate:
    key: TemplateKey
    name: str
    description: str
    requires_tags: bool


# Tag'in görünen etiketi: açıklama varsa onu, boşsa teknik ada düş.
_TAG_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"

# (old emitted substring, new substring) — exact, order matters. More specific
# patterns first so prefixes (e.g. breach "SELECT t.name, sum") are not shadowed
# by the generic subquery "SELECT t.name, t.device" replacement.
_LABEL_SWAPS: tuple[tuple[str, str], ...] = (
    ("t.name AS metric", f"{_TAG_LABEL} AS metric"),
    (
        "SELECT DISTINCT ON (t.id) t.name,",
        f'SELECT DISTINCT ON (t.id) {_TAG_LABEL} AS "Etiket",',
    ),
    ("SELECT t.name, sum(CASE", f'SELECT {_TAG_LABEL} AS "Etiket", sum(CASE'),
    # subquery tables: inner label first, then outer readable header
    ("SELECT t.id AS tid, t.name,", f"SELECT t.id AS tid, {_TAG_LABEL} AS name,"),
    ("SELECT t.name, t.device,", f"SELECT {_TAG_LABEL} AS name, t.device,"),
    (
        "SELECT name, value, unit, quality, timestamp FROM (",
        'SELECT name AS "Etiket", value, unit, quality, timestamp FROM (',
    ),
    (
        "SELECT name, device, value, unit, quality, timestamp FROM (",
        'SELECT name AS "Etiket", device, value, unit, quality, timestamp FROM (',
    ),
)


def apply_tag_label(sql: str) -> str:
    """Rewrite the technical-name label substrings older generators emitted to
    use _TAG_LABEL. Pure + idempotent: if the SQL already references the label
    expression, or contains no known pattern, it is returned unchanged."""
    if "COALESCE(NULLIF(t.description" in sql:
        return sql
    out = sql
    for old, new in _LABEL_SWAPS:
        out = out.replace(old, new)
    return out


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
    datasource: dict | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
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
        "targets": [target or {"refId": "A", "format": "time_series", "rawSql": raw_sql}],
    }


def _stat_panel(
    panel_id: int,
    title: str,
    raw_sql: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    datasource: dict | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "id": panel_id,
        "type": "stat",
        "title": title,
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
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
        "targets": [target or {"refId": "A", "format": "table", "rawSql": raw_sql}],
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
    datasource: dict | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "id": panel_id,
        "type": "table",
        "title": title,
        "datasource": datasource or {"type": "postgres", "uid": "timescaledb"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [target or {"refId": "A", "format": "table", "rawSql": raw_sql}],
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
    ds = _frser_datasource()
    tag_count_sql = 'SELECT count(*) AS "Tag" FROM tags'
    last_read_sql = (
        "SELECT CAST(strftime('%s', max(timestamp)) AS INTEGER) * 1000 "
        'AS "Son Okuma" FROM tag_readings'
    )
    reads_24h_sql = (
        'SELECT count(*) AS "Okuma" FROM tag_readings '
        "WHERE timestamp >= datetime('now', '-24 hours')"
    )
    bad_pct_sql = (
        "SELECT 100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
        '/ NULLIF(count(*), 0) AS "BAD %" FROM tag_readings '
        "WHERE timestamp >= datetime('now', '-24 hours')"
    )
    volume_sql = (
        "SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 300) * 300 AS time, "
        'count(*) AS "Okuma" FROM tag_readings '
        "WHERE timestamp >= datetime('now', '-24 hours') GROUP BY 1 ORDER BY 1"
    )
    bad_rate_sql = (
        "SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 900) * 900 AS time, "
        "100.0 * sum(CASE WHEN quality <> 192 THEN 1 ELSE 0 END) "
        '/ NULLIF(count(*), 0) AS "BAD %" FROM tag_readings '
        "WHERE timestamp >= datetime('now', '-24 hours') GROUP BY 1 ORDER BY 1"
    )
    last_values_sql = (
        'SELECT name AS "Etiket", device, value, unit, quality, timestamp FROM ('
        f"SELECT {_TAG_LABEL} AS name, t.device, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id"
        ") WHERE rn = 1 ORDER BY timestamp DESC LIMIT 20"
    )
    return _base_dashboard(
        uid,
        title,
        ["facility-overview"],
        [
            _stat_panel(
                1,
                "Toplam Tag",
                tag_count_sql,
                x=0,
                y=0,
                w=6,
                h=5,
                datasource=ds,
                target=_frser_target(tag_count_sql, time_series=False),
            ),
            _stat_panel(
                2,
                "Son Okuma",
                last_read_sql,
                x=6,
                y=0,
                w=6,
                h=5,
                datasource=ds,
                target=_frser_target(last_read_sql, time_series=False),
            ),
            _stat_panel(
                3,
                "Son 24s Okuma",
                reads_24h_sql,
                x=12,
                y=0,
                w=6,
                h=5,
                datasource=ds,
                target=_frser_target(reads_24h_sql, time_series=False),
            ),
            _stat_panel(
                4,
                "BAD Kalite %",
                bad_pct_sql,
                x=18,
                y=0,
                w=6,
                h=5,
                datasource=ds,
                target=_frser_target(bad_pct_sql, time_series=False),
            ),
            _timeseries_panel(
                5,
                "Okuma Hacmi",
                volume_sql,
                x=0,
                y=5,
                w=12,
                h=8,
                datasource=ds,
                target=_frser_target(volume_sql, time_series=True),
            ),
            _timeseries_panel(
                6,
                "BAD Kalite Oranı",
                bad_rate_sql,
                x=12,
                y=5,
                w=12,
                h=8,
                unit="percent",
                datasource=ds,
                target=_frser_target(bad_rate_sql, time_series=True),
            ),
            _table_panel(
                7,
                "Son Değerler",
                last_values_sql,
                x=0,
                y=13,
                w=24,
                h=8,
                datasource=ds,
                target=_frser_target(last_values_sql, time_series=False),
            ),
        ],
    )


def build_water_quality_dashboard(uid: str, title: str, tag_ids: list[int]) -> dict:
    ids = _tag_filter(tag_ids)
    ds = _frser_datasource()
    trend_sql = (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        f"{_TAG_LABEL} AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND tr.tag_id IN ({ids}) "
        "ORDER BY time"
    )
    latest_sql = (
        'SELECT name AS "Etiket", value, unit, quality, timestamp FROM ('
        f"SELECT t.id AS tid, {_TAG_LABEL} AS name, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE t.id IN ({ids})"
        ") WHERE rn = 1 ORDER BY tid"
    )
    breach_sql = (
        f'SELECT {_TAG_LABEL} AS "Etiket", '
        "sum(CASE WHEN t.min_alarm IS NOT NULL "
        'AND tr.value < t.min_alarm THEN 1 ELSE 0 END) AS "Alt Limit", '
        "sum(CASE WHEN t.max_alarm IS NOT NULL "
        'AND tr.value > t.max_alarm THEN 1 ELSE 0 END) AS "Üst Limit" '
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id "
        f"WHERE tr.timestamp >= datetime('now', '-7 days') AND t.id IN ({ids}) "
        "GROUP BY t.name ORDER BY t.name"
    )
    dash = _base_dashboard(
        uid,
        title,
        ["water-quality"],
        [
            _timeseries_panel(
                1,
                "Su Kalitesi Trendleri",
                trend_sql,
                x=0,
                y=0,
                w=24,
                h=11,
                datasource=ds,
                target=_frser_target(trend_sql, time_series=True),
            ),
            _table_panel(
                2,
                "Son Değerler",
                latest_sql,
                x=0,
                y=11,
                w=12,
                h=8,
                datasource=ds,
                target=_frser_target(latest_sql, time_series=False),
            ),
            _table_panel(
                3,
                "Limit Aşımı Özeti",
                breach_sql,
                x=12,
                y=11,
                w=12,
                h=8,
                datasource=ds,
                target=_frser_target(breach_sql, time_series=False),
            ),
        ],
    )
    dash["time"] = {"from": "now-7d", "to": "now"}
    return dash


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


def _frser_datasource() -> dict:
    return {"type": "frser-sqlite-datasource", "uid": settings.GRAFANA_DATASOURCE_UID}


def _frser_target(sql: str, *, time_series: bool) -> dict:
    return {
        "refId": "A",
        "datasource": _frser_datasource(),
        "queryType": "time series" if time_series else "table",
        "queryText": sql,
        "rawQueryText": sql,
        "timeColumns": ["time"],
    }


def _lab_timeseries_panel(panel_id: int, point_code: str, param: LabParamSpec, *, y: int) -> dict:
    """A v_lab_timeseries (frser-sqlite) time-series panel for one parameter, with limit lines."""
    sql = (
        f"SELECT CAST(strftime('%s', time) AS INTEGER) AS time, param_name AS metric, value "
        f"FROM v_lab_timeseries "
        f"WHERE point_code = {_lab_sql_code(point_code)} "
        f"AND param_code = {_lab_sql_code(param.code)} "
        f"ORDER BY time"
    )
    title = f"{param.name}{f' ({param.unit})' if param.unit else ''}"
    steps: list[dict] = [{"color": "green", "value": None}]
    if param.min_limit is not None:
        steps.append({"color": "orange", "value": param.min_limit})
    if param.max_limit is not None:
        steps.append({"color": "red", "value": param.max_limit})
    # Grafana wants steps sorted ascending; the base None step stays first.
    steps[1:] = sorted(steps[1:], key=lambda s: s["value"])
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": _frser_datasource(),
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 8},
        "fieldConfig": {
            "defaults": {
                "unit": param.unit or "short",
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "showPoints": "always",
                    "pointSize": 6,
                    "spanNulls": True,
                    "thresholdsStyle": {"mode": "line"},
                },
                "color": {"mode": "palette-classic"},
                "thresholds": {"mode": "absolute", "steps": steps},
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
        "targets": [_frser_target(sql, time_series=True)],
    }


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
        f"ORDER BY time DESC LIMIT 200"
    )
    panels.append(
        {
            "id": len(params) + 1,
            "type": "table",
            "title": "Son değerler",
            "datasource": _frser_datasource(),
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 10},
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {"showHeader": True},
            "targets": [_frser_target(table_sql, time_series=False)],
        }
    )
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
                    "SELECT $__time(tr.timestamp) AS time, "
                    f"{_TAG_LABEL} AS metric, tr.value AS value "
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
                    f'SELECT DISTINCT ON (t.id) {_TAG_LABEL} AS "Etiket", '
                    "tr.value, t.unit, tr.quality, tr.timestamp "
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
                    f'SELECT {_TAG_LABEL} AS "Etiket", '
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
