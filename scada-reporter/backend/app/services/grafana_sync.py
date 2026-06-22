from __future__ import annotations

import httpx


def _query(group_id: int) -> str:
    return (
        "SELECT CAST(strftime('%s', tr.timestamp) AS INTEGER) AS time, "
        "t.name AS metric, tr.value AS value "
        "FROM tag_readings tr JOIN tags t ON t.id = tr.tag_id "
        "WHERE tr.tag_id IN "
        f"(SELECT tag_id FROM watchlist_group_members WHERE group_id = {group_id}) "
        "AND tr.timestamp >= datetime('now','-6 hours') ORDER BY time"
    )


def build_group_dashboard(group_id: int, name: str, datasource_uid: str = "scadadb") -> dict:
    ds = {"type": "frser-sqlite-datasource", "uid": datasource_uid}
    sql = _query(group_id)
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


async def sync_groups(groups: list[tuple[int, str]], *, http: httpx.AsyncClient) -> dict:
    """Push one dashboard per group; delete stale wl-group-* dashboards.

    `http` is a configured AsyncClient (base_url + auth). Returns counts + errors.
    """
    written = 0
    errors: list[str] = []
    wanted_uids = {f"wl-group-{gid}" for gid, _ in groups}

    for gid, name in groups:
        dash = build_group_dashboard(gid, name)
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
