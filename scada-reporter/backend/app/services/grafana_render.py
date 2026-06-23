from __future__ import annotations

import re

import httpx

from app.core.config import settings

# Strict allowlist for Grafana dashboard UIDs (alphanumeric, dash, underscore; max 64 chars).
_DASHBOARD_UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def render_auth() -> tuple[str, str] | None:
    """Basic-auth fallback; SA token varsa None (header ile gider)."""
    if settings.GRAFANA_SA_TOKEN:
        return None
    return (settings.GRAFANA_USER, settings.GRAFANA_PASSWORD)


def render_headers() -> dict[str, str]:
    if settings.GRAFANA_SA_TOKEN:
        return {"Authorization": f"Bearer {settings.GRAFANA_SA_TOKEN}"}
    return {}


async def render_panel(
    *,
    dashboard_uid: str,
    panel_id: int,
    from_ms: int,
    to_ms: int,
    http: httpx.AsyncClient,
    theme: str = "light",
    width: int = 1000,
    height: int = 500,
    tz: str = "UTC",
) -> bytes:
    """Grafana /render/d-solo'dan panel PNG'si çek. Hata olursa b"" döner (raporu düşürmez)."""
    # Defense-in-depth: reject any stored uid that bypassed schema validation.
    if not _DASHBOARD_UID_RE.match(dashboard_uid):
        return b""
    params: dict[str, str | int] = {
        "panelId": panel_id,
        "from": from_ms,
        "to": to_ms,
        "width": width,
        "height": height,
        "theme": theme,
        "tz": tz,
        "kiosk": "",
    }
    try:
        r = await http.get(
            f"/render/d-solo/{dashboard_uid}/_",
            params=params,
            headers=render_headers(),
        )
        if r.status_code >= 400:
            return b""
        return r.content
    except httpx.HTTPError:
        return b""
