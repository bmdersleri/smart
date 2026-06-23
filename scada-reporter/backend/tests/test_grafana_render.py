# tests/test_grafana_render.py
import httpx
import pytest

from app.services.grafana_render import render_panel


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"fakepngdata"


@pytest.mark.asyncio
async def test_render_panel_returns_png_and_builds_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(
            dashboard_uid="scada-watchlist",
            panel_id=2,
            from_ms=1000,
            to_ms=2000,
            http=http,
        )

    assert out == _png()
    assert seen["path"] == "/render/d-solo/scada-watchlist/_"
    assert seen["params"]["panelId"] == "2"
    assert seen["params"]["from"] == "1000"
    assert seen["params"]["to"] == "2000"
    assert seen["params"]["theme"] == "light"


@pytest.mark.asyncio
async def test_render_panel_swallows_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(dashboard_uid="x", panel_id=1, from_ms=0, to_ms=1, http=http)
    assert out == b""


@pytest.mark.asyncio
async def test_render_panel_swallows_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://gf") as http:
        out = await render_panel(dashboard_uid="x", panel_id=1, from_ms=0, to_ms=1, http=http)
    assert out == b""
