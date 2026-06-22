import httpx
import pytest

from app.services.grafana_sync import build_group_dashboard, sync_groups


def test_build_group_dashboard_shape():
    d = build_group_dashboard(7, "Pompalar")
    assert d["uid"] == "wl-group-7"
    assert "Pompalar" in d["title"]
    assert "watchlist-group" in d["tags"]
    sql = d["panels"][0]["targets"][0]["rawQueryText"]
    assert "group_id = 7" in sql
    assert "strftime('%s'" in sql  # epoch seconds, not ms
    assert d["panels"][0]["targets"][0]["datasource"]["uid"] == "scadadb"


@pytest.mark.asyncio
async def test_sync_groups_writes_and_deletes_stale():
    calls = {"posts": [], "deletes": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            # one stale generated dashboard exists (wl-group-99)
            return httpx.Response(200, json=[{"uid": "wl-group-99", "tags": ["watchlist-group"]}])
        if request.url.path == "/api/dashboards/db":
            calls["posts"].append(request)
            return httpx.Response(200, json={"status": "success"})
        if request.url.path.startswith("/api/dashboards/uid/"):
            calls["deletes"].append(request.url.path)
            return httpx.Response(200, json={"title": "deleted"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        result = await sync_groups([(1, "A"), (2, "B")], http=http)

    assert result["written"] == 2
    assert result["deleted"] == 1  # wl-group-99 no longer a real group
    assert "/api/dashboards/uid/wl-group-99" in calls["deletes"]
    assert result["errors"] == []
