from __future__ import annotations

import json as _json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.license_guard import require_feature
from app.core.config import settings
from app.core.database import get_db
from app.models.report_template import ReportTemplate
from app.models.tag import Tag
from app.models.user import User
from app.services.grafana_render import render_auth, render_headers
from app.services.grafana_templates import (
    build_dashboard,
    build_report_template_dashboard,
    dashboard_uid,
    get_template,
    list_templates,
    report_dashboard_uid,
)

router = APIRouter(prefix="/grafana", tags=["grafana"])

_transport = None  # httpx.MockTransport | None — testlerde monkeypatch'lenir


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


@router.post("/dashboards/from-report-template/{template_id}")
async def generate_from_report_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _feature=Depends(require_feature("grafana")),
) -> dict:
    tmpl = await db.get(ReportTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")

    tag_ids = _json.loads(tmpl.tag_ids or "[]")
    if not tag_ids:
        raise HTTPException(status_code=422, detail="Dashboard için tag'li bir şablon gerekir")

    rows = (
        (await db.execute(select(Tag.id).where(Tag.id.in_(tag_ids), Tag.is_active.is_(True))))
        .scalars()
        .all()
    )
    missing = sorted(set(tag_ids) - set(rows))
    if missing:
        raise HTTPException(status_code=404, detail={"missing_tag_ids": missing})

    dashboard = build_report_template_dashboard(
        template_id=tmpl.id,
        title=tmpl.name,
        tag_ids=tag_ids,
        time_range_type=tmpl.time_range_type,
        custom_start=tmpl.custom_start,
        custom_end=tmpl.custom_end,
        show_trend_charts=tmpl.show_trend_charts,
        show_summary_stats=tmpl.show_summary_stats,
        anomaly_enabled=tmpl.anomaly_enabled,
        show_anomaly_table=tmpl.show_anomaly_table,
    )

    try:
        async with httpx.AsyncClient(
            base_url=settings.GRAFANA_URL,
            auth=render_auth(),
            headers=render_headers(),
            timeout=10.0,
            transport=_transport,
        ) as http:
            response = await http.post(
                "/api/dashboards/db",
                json={"dashboard": dashboard, "overwrite": True},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Grafana erişilemedi: {e}") from None

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Grafana dashboard yazılamadı: HTTP {response.status_code}"
        )

    payload = response.json()
    return {
        "uid": report_dashboard_uid(tmpl.id),
        "title": tmpl.name,
        "url": payload.get("url") or f"/d/{report_dashboard_uid(tmpl.id)}",
        "template_id": tmpl.id,
        "status": payload.get("status", "success"),
    }
