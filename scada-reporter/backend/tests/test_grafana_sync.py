import httpx
import pytest

from app.services.grafana_sync import build_group_dashboard, split_high_axis, sync_groups


def test_build_group_dashboard_shape():
    d = build_group_dashboard(7, "Pompalar")
    assert d["uid"] == "wl-group-7"
    assert "Pompalar" in d["title"]
    assert "watchlist-group" in d["tags"]
    sql = d["panels"][0]["targets"][0]["rawQueryText"]
    assert "group_id = 7" in sql
    assert "strftime('%s'" in sql  # epoch seconds, not ms
    assert d["panels"][0]["targets"][0]["datasource"]["uid"] == "scadadb"
    assert d["panels"][0]["fieldConfig"]["overrides"] == []  # ayrım yoksa temiz


def test_build_group_dashboard_rejects_non_integer_group_id():
    with pytest.raises(ValueError):
        build_group_dashboard("7 OR 1=1", "Pompalar")  # type: ignore[arg-type]


def test_split_high_axis_separates_large_scale_tags():
    # küçükler ~2-8, biri ~2000 -> büyük olan sağ eksene
    mags = {"seviye": 5.0, "debi": 8.0, "basinc": 2.0, "toplam_hacim": 2000.0}
    assert split_high_axis(mags) == ["toplam_hacim"]


def test_split_high_axis_no_split_when_similar():
    assert split_high_axis({"a": 10.0, "b": 12.0, "c": 9.0}) == []


def test_split_high_axis_ignores_zero_and_single():
    assert split_high_axis({"a": 0.0, "b": 0.0}) == []
    assert split_high_axis({"only": 100.0}) == []


def test_build_dashboard_places_high_tags_on_right_axis():
    d = build_group_dashboard(3, "Grup", right_axis_tags=["toplam_hacim"])
    overrides = d["panels"][0]["fieldConfig"]["overrides"]
    assert len(overrides) == 1
    # frser serileri "value <ad>" oldugu icin sona-sabitli regexp ile eslesir
    assert overrides[0]["matcher"] == {"id": "byRegexp", "options": "/toplam_hacim$/"}
    assert overrides[0]["properties"][0] == {"id": "custom.axisPlacement", "value": "right"}
    assert d["panels"][0]["fieldConfig"]["defaults"]["custom"]["axisPlacement"] == "left"


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
