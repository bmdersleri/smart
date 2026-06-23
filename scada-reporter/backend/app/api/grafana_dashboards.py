from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.config import settings
from app.core.database import get_db
from app.models.tag import Tag
from app.models.user import User
from app.services.grafana_templates import (
    build_dashboard,
    dashboard_uid,
    get_template,
    list_templates,
)

router = APIRouter(prefix="/grafana", tags=["grafana"])


class DashboardGenerateIn(BaseModel):
    template: str
    title: str = Field(min_length=1, max_length=120)
    tag_ids: list[int] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title boş olamaz")
        return v

    @field_validator("tag_ids")
    @classmethod
    def _unique_positive_tags(cls, v: list[int]) -> list[int]:
        return sorted({int(tag_id) for tag_id in v if int(tag_id) > 0})


@router.get("/templates")
async def grafana_templates(
    _user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
):
    return {"templates": list_templates()}


@router.post("/dashboards/generate")
async def generate_dashboard(
    body: DashboardGenerateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
):
    try:
        template = get_template(body.template)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    if template.requires_tags and not body.tag_ids:
        raise HTTPException(status_code=422, detail="Bu şablon için en az bir tag seçin")

    if body.tag_ids:
        rows = (
            (
                await db.execute(
                    select(Tag.id).where(Tag.id.in_(body.tag_ids), Tag.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        found = set(rows)
        missing = sorted(set(body.tag_ids) - found)
        if missing:
            raise HTTPException(status_code=404, detail={"missing_tag_ids": missing})

    uid = dashboard_uid(template.key, user.id, body.title, body.tag_ids)
    dashboard = build_dashboard(template.key, uid, body.title, body.tag_ids)

    auth = (settings.GRAFANA_USER, settings.GRAFANA_PASSWORD)
    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=auth,
            timeout=10.0,
        ) as http:
            response = await http.post(
                "/api/dashboards/db",
                json={"dashboard": dashboard, "overwrite": True},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Grafana dashboard yazılamadı: HTTP {response.status_code}",
        )

    payload = response.json()
    grafana_path = payload.get("url") or f"/d/{uid}"
    return {
        "uid": uid,
        "title": body.title,
        "url": grafana_path,
        "template": template.key,
        "status": payload.get("status", "success"),
    }
