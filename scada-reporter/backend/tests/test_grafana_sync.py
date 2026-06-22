from app.services.grafana_sync import build_group_dashboard


def test_build_group_dashboard_shape():
    d = build_group_dashboard(7, "Pompalar")
    assert d["uid"] == "wl-group-7"
    assert "Pompalar" in d["title"]
    assert "watchlist-group" in d["tags"]
    sql = d["panels"][0]["targets"][0]["rawQueryText"]
    assert "group_id = 7" in sql
    assert "strftime('%s'" in sql  # epoch seconds, not ms
    assert d["panels"][0]["targets"][0]["datasource"]["uid"] == "scadadb"
