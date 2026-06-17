from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.services.ai_service import (
    detect_anomalies,
    generate_ai_report,
    get_system_health,
    parse_natural_language_query,
    predict_trend,
    resolve_tag_names,
)

router = APIRouter(prefix="/ai", tags=["ai"])


class NLQueryRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, description="Natural language question about SCADA data"
    )


class AnomalyRequest(BaseModel):
    tag_name: str
    window: str = "7d"
    threshold: float = 3.0


class PredictRequest(BaseModel):
    tag_name: str
    horizon: str = "24h"


class ReportRequest(BaseModel):
    tags: list[str]
    start: str
    end: str
    format: str = "excel"
    aggregation: str = "raw"


class AIHealthResponse(BaseModel):
    status: str = "ok"
    ai_services: list[str]
    model_config = {"from_attributes": True}


@router.get("/health")
async def ai_health(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    health = await get_system_health(db)
    return {"status": "ok", "ai_services": health["ai_services"]}


@router.post("/query")
async def natural_language_query(
    request: NLQueryRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await parse_natural_language_query(db, request.question)
    return {
        "question": result.question,
        "answer": result.answer,
        "data": result.data,
        "chart_config": result.chart_config,
    }


@router.post("/anomalies")
async def anomaly_detection(
    request: AnomalyRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await detect_anomalies(db, request.tag_name, request.window, request.threshold)
    return {
        "tag_name": result.tag_name,
        "tag_id": result.tag_id,
        "total_readings": result.total_readings,
        "anomaly_rate_pct": result.anomaly_rate_pct,
        "anomalies": [
            {
                "timestamp": a.timestamp.isoformat()
                if hasattr(a.timestamp, "isoformat")
                else str(a.timestamp),
                "value": a.value,
                "type": a.anomaly_type,
                "severity": a.severity,
                "details": a.details,
            }
            for a in result.anomalies
        ],
    }


@router.post("/predict")
async def trend_prediction(
    request: PredictRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await predict_trend(db, request.tag_name, request.horizon)
    return {
        "tag_name": result.tag_name,
        "tag_id": result.tag_id,
        "trend_direction": result.trend_direction,
        "slope": result.slope,
        "forecast": result.forecast,
        "confidence_interval": {
            "lower": result.confidence_lower,
            "upper": result.confidence_upper,
        },
    }


@router.post("/reports/generate")
async def ai_report_generation(
    request: ReportRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await generate_ai_report(
        db,
        request.tags,
        request.start,
        request.end,
        request.format,
        request.aggregation,
    )
    return result


@router.post("/resolve")
async def resolve_tags(
    descriptions: list[str],
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    tag_ids = await resolve_tag_names(db, descriptions)
    return {"tag_ids": tag_ids, "matched": len(tag_ids)}
