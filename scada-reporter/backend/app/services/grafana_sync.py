from __future__ import annotations


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
