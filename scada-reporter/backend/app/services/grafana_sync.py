from __future__ import annotations

import math
import re

import httpx


def split_high_axis(magnitudes: dict[str, float], *, min_ratio: float = 8.0) -> list[str]:
    """Bir gruptaki tag'leri büyüklüğe göre ikiye ayırıp 'yüksek' olanları döndür.

    Aynı panelde çok farklı ölçekli tag'ler birbirini ezer. Burada her tag'in son
    büyüklüğüne (|değer| tepe) bakıp, sıralı büyüklükler arasındaki en büyük
    log-aralıktan bölüyoruz: üstte kalanlar sağ Y eksenine atanır.

    - 0/None büyüklükler yok sayılır (eksen kararına katılmaz).
    - En büyük/en küçük oranı `min_ratio` altındaysa ayrım yapılmaz (boş liste).
    """
    pos = {name: float(m) for name, m in magnitudes.items() if m and m > 0}
    if len(pos) < 2:
        return []

    ordered = sorted(pos.items(), key=lambda kv: kv[1])  # küçükten büyüğe
    lo, hi = ordered[0][1], ordered[-1][1]
    if hi / lo < min_ratio:
        return []  # hepsi benzer ölçekte; tek eksen yeter

    # Ardışık büyüklükler arasındaki en büyük log-aralığı bul; oradan böl.
    best_gap = 0.0
    split_idx = len(ordered) - 1  # en azından en büyüğü ayır
    for i in range(1, len(ordered)):
        gap = math.log10(ordered[i][1]) - math.log10(ordered[i - 1][1])
        if gap > best_gap:
            best_gap = gap
            split_idx = i

    return [name for name, _ in ordered[split_idx:]]


def _axis_overrides(right_axis_tags: list[str]) -> list[dict]:
    # frser long-format serileri "value <tag adı>" olarak adlanır; bu yüzden tam
    # ad yerine tag adını SONA sabitleyen regexp ile eşleştiriyoruz (prefix'ten
    # bağımsız, sağlam). re.escape nokta/tire gibi özel karakterleri kaçırır.
    return [
        {
            "matcher": {"id": "byRegexp", "options": f"/{re.escape(name)}$/"},
            "properties": [{"id": "custom.axisPlacement", "value": "right"}],
        }
        for name in right_axis_tags
    ]


def _query(group_id: int) -> str:
    safe_group_id = int(group_id)
    return (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        "t.name AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        "WHERE tr.tag_id IN "
        f"(SELECT tag_id FROM watchlist_group_members WHERE group_id = {safe_group_id}) "  # nosec B608
        "AND tr.timestamp >= datetime('now','-6 hours') ORDER BY time"
    )


def build_group_dashboard(
    group_id: int,
    name: str,
    datasource_uid: str = "scadadb",
    right_axis_tags: list[str] | None = None,
) -> dict:
    ds = {"type": "frser-sqlite-datasource", "uid": datasource_uid}
    sql = _query(group_id)
    overrides = _axis_overrides(right_axis_tags or [])
    return {
        "uid": f"wl-group-{group_id}",
        "title": f"Watchlist — {name}",
        "tags": ["scada", "watchlist-group"],
        "timezone": "browser",
        "schemaVersion": 39,
        "refresh": "10s",
        "time": {"from": "now-6h", "to": "now"},
        "panels": [
            {
                "id": 1,
                "type": "timeseries",
                "title": name,
                "datasource": ds,
                "gridPos": {"h": 18, "w": 24, "x": 0, "y": 0},
                "fieldConfig": {
                    "defaults": {
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 1,
                            "fillOpacity": 8,
                            "showPoints": "never",
                            "spanNulls": True,
                            "axisPlacement": "left",
                        },
                        "color": {"mode": "palette-classic"},
                    },
                    "overrides": overrides,
                },
                "options": {
                    "legend": {
                        "displayMode": "table",
                        "placement": "right",
                        "calcs": ["last", "min", "max"],
                    },
                    "tooltip": {"mode": "multi", "sort": "desc"},
                },
                "targets": [
                    {
                        "refId": "A",
                        "datasource": ds,
                        "queryType": "time series",
                        "timeColumns": ["time"],
                        "rawQueryText": sql,
                        "queryText": sql,
                    }
                ],
            }
        ],
    }


async def sync_groups(
    groups: list[tuple[int, str]],
    *,
    http: httpx.AsyncClient,
    magnitudes: dict[int, dict[str, float]] | None = None,
) -> dict:
    """Push one dashboard per group; delete stale wl-group-* dashboards.

    `http` is a configured AsyncClient (base_url + auth). `magnitudes` maps
    group_id -> {tag_name: |value| tepe}; verildiğinde yüksek ölçekli tag'ler
    otomatik sağ Y eksenine atanır. Returns counts + errors.
    """
    written = 0
    errors: list[str] = []
    wanted_uids = {f"wl-group-{gid}" for gid, _ in groups}
    mags = magnitudes or {}

    for gid, name in groups:
        right_axis = split_high_axis(mags.get(gid, {}))
        dash = build_group_dashboard(gid, name, right_axis_tags=right_axis)
        try:
            r = await http.post("/api/dashboards/db", json={"dashboard": dash, "overwrite": True})
            if r.status_code >= 400:
                errors.append(f"write {gid}: HTTP {r.status_code}")
            else:
                written += 1
        except httpx.HTTPError as e:
            errors.append(f"write {gid}: {e}")

    deleted = 0
    try:
        sr = await http.get("/api/search", params={"tag": "watchlist-group"})
        existing = sr.json() if sr.status_code < 400 else []
    except httpx.HTTPError as e:
        existing = []
        errors.append(f"search: {e}")
    for item in existing:
        uid = item.get("uid", "")
        if uid.startswith("wl-group-") and uid not in wanted_uids:
            try:
                dr = await http.delete(f"/api/dashboards/uid/{uid}")
                if dr.status_code < 400:
                    deleted += 1
                else:
                    errors.append(f"delete {uid}: HTTP {dr.status_code}")
            except httpx.HTTPError as e:
                errors.append(f"delete {uid}: {e}")

    return {"written": written, "deleted": deleted, "errors": errors}
