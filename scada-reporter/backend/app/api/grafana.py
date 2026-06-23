from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.config import settings
from app.models.user import User
from app.services.grafana_render import render_auth, render_headers

router = APIRouter(prefix="/grafana", tags=["grafana"])

# Test injection override — None in production (real network).
_transport: httpx.MockTransport | None = None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.GRAFANA_URL,
        auth=render_auth(),
        headers=render_headers(),
        timeout=10.0,
        transport=_transport,
    )


@router.get("/dashboards")
async def list_dashboards(
    _user: User = Depends(get_current_user),
    _=Depends(require_feature("grafana")),
) -> list[dict]:
    try:
        async with _client() as http:
            r = await http.get("/api/search", params={"type": "dash-db"})
            r.raise_for_status()
            rows = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    return [{"uid": d["uid"], "title": d["title"]} for d in rows if d.get("uid")]


@router.get("/dashboards/{uid}/panels")
async def list_panels(
    uid: str,
    _user: User = Depends(get_current_user),
    _=Depends(require_feature("grafana")),
) -> list[dict]:
    try:
        async with _client() as http:
            r = await http.get(f"/api/dashboards/uid/{uid}")
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None
    panels = body.get("dashboard", {}).get("panels", [])
    return [
        {"id": p["id"], "title": p["title"]}
        for p in panels
        if p.get("type") != "row" and p.get("title")
    ]
