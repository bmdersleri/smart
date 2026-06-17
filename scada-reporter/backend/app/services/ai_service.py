import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TagReading
from app.services.stats_engine import AnomalyEvent

logger = logging.getLogger(__name__)


@dataclass
class AnomalyResult:
    tag_name: str
    tag_id: int
    anomalies: list[AnomalyEvent]
    total_readings: int
    anomaly_rate_pct: float


@dataclass
class PredictionResult:
    tag_name: str
    tag_id: int
    forecast: list[dict[str, Any]]
    confidence_lower: list[float]
    confidence_upper: list[float]
    trend_direction: str
    slope: float


@dataclass
class NLQueryResult:
    question: str
    answer: str
    data: list[dict[str, Any]] | None
    chart_config: dict[str, Any] | None


async def resolve_tag_names(db: AsyncSession, descriptions: list[str]) -> list[int]:
    """Resolve tag names or descriptions to tag IDs using fuzzy matching."""
    ids: list[int] = []
    for desc in descriptions:
        result = await db.execute(
            select(Tag.id).where(Tag.name.ilike(f"%{desc}%"), Tag.is_active).limit(5)
        )
        matched = result.scalars().all()
        ids.extend(matched)
    return list(set(ids))


async def detect_anomalies(
    db: AsyncSession,
    tag_name: str,
    window: str = "7d",
    z_threshold: float = 3.0,
) -> AnomalyResult:
    result = await db.execute(select(Tag).where(Tag.name == tag_name))
    tag = result.scalar_one_or_none()
    if not tag:
        return AnomalyResult(
            tag_name=tag_name, tag_id=0, anomalies=[], total_readings=0, anomaly_rate_pct=0.0
        )

    seconds = _parse_window(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    rows = await db.execute(
        select(TagReading.timestamp, TagReading.value, TagReading.quality)
        .where(
            TagReading.tag_id == tag.id,
            TagReading.timestamp >= since,
            TagReading.quality == 192,
        )
        .order_by(TagReading.timestamp)
    )
    readings = rows.all()

    if not readings:
        return AnomalyResult(
            tag_name=tag_name, tag_id=tag.id, anomalies=[], total_readings=0, anomaly_rate_pct=0.0
        )

    values = np.array([r.value for r in readings if r.value is not None], dtype=float)
    timestamps = [r.timestamp for r in readings if r.value is not None]

    if len(values) < 5:
        return AnomalyResult(
            tag_name=tag_name,
            tag_id=tag.id,
            anomalies=[],
            total_readings=len(values),
            anomaly_rate_pct=0.0,
        )

    mean = np.mean(values)
    std = np.std(values)
    anomalies: list[AnomalyEvent] = []

    if std < 1e-10:
        return AnomalyResult(
            tag_name=tag_name,
            tag_id=tag.id,
            anomalies=[],
            total_readings=len(values),
            anomaly_rate_pct=0.0,
        )

    for i in range(len(values)):
        z = abs(values[i] - mean) / std
        if z > z_threshold:
            anomalies.append(
                AnomalyEvent(
                    timestamp=timestamps[i],
                    value=float(values[i]),
                    anomaly_type="zscore",
                    severity="critical" if z > z_threshold * 1.5 else "warning",
                    details=f"Z-score: {z:.2f}, mean: {float(mean):.2f}, std: {float(std):.2f}",
                )
            )

    # Jump detection: consecutive readings with large delta
    for i in range(1, len(values)):
        delta = abs(values[i] - values[i - 1])
        if delta > 3 * std and delta > abs(mean) * 0.5 if abs(mean) > 0 else delta > std:
            anomalies.append(
                AnomalyEvent(
                    timestamp=timestamps[i],
                    value=float(values[i]),
                    anomaly_type="jump",
                    severity="warning",
                    details=(
                        f"Sudden change: {float(values[i - 1]):.2f} -> "
                        f"{float(values[i]):.2f} (delta={float(delta):.2f})"
                    ),
                )
            )

    rate = (len(anomalies) / len(values)) * 100 if values.size > 0 else 0.0
    return AnomalyResult(
        tag_name=tag_name,
        tag_id=tag.id,
        anomalies=anomalies,
        total_readings=len(values),
        anomaly_rate_pct=round(rate, 2),
    )


async def predict_trend(
    db: AsyncSession,
    tag_name: str,
    horizon: str = "24h",
) -> PredictionResult:
    result = await db.execute(select(Tag).where(Tag.name == tag_name))
    tag = result.scalar_one_or_none()
    if not tag:
        return PredictionResult(
            tag_name=tag_name,
            tag_id=0,
            forecast=[],
            confidence_lower=[],
            confidence_upper=[],
            trend_direction="unknown",
            slope=0.0,
        )

    lookback = "7d" if "h" in horizon else "30d"
    seconds = _parse_window(lookback)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    rows = await db.execute(
        select(TagReading.timestamp, TagReading.value)
        .where(
            TagReading.tag_id == tag.id,
            TagReading.timestamp >= since,
            TagReading.quality == 192,
            TagReading.value.isnot(None),
        )
        .order_by(TagReading.timestamp)
    )
    readings = rows.all()

    if len(readings) < 10:
        return PredictionResult(
            tag_name=tag_name,
            tag_id=tag.id,
            forecast=[],
            confidence_lower=[],
            confidence_upper=[],
            trend_direction="insufficient_data",
            slope=0.0,
        )

    # Simple linear regression for trend
    values = np.array([r.value for r in readings], dtype=float)
    x = np.arange(len(values))
    slope, intercept = np.polyfit(x, values, 1)
    trend = "rising" if slope > 0.001 else "falling" if slope < -0.001 else "stable"

    # Project forward
    horizon_seconds = _parse_window(horizon)
    avg_interval = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / max(
        len(readings) - 1, 1
    )
    steps = int(horizon_seconds / max(avg_interval, 1))
    steps = min(steps, 500)

    resid = values - (intercept + slope * x)
    resid_std = np.std(resid)

    last_ts = readings[-1].timestamp
    forecast = []
    lower = []
    upper = []

    for i in range(1, steps + 1):
        ts = last_ts + timedelta(seconds=avg_interval * i)
        x_future = len(values) + i - 1
        y_hat = intercept + slope * x_future
        forecast.append({"timestamp": ts.isoformat(), "value": round(float(y_hat), 4)})
        lower.append(round(float(y_hat - 2 * resid_std), 4))
        upper.append(round(float(y_hat + 2 * resid_std), 4))

    return PredictionResult(
        tag_name=tag_name,
        tag_id=tag.id,
        forecast=forecast,
        confidence_lower=lower,
        confidence_upper=upper,
        trend_direction=trend,
        slope=round(float(slope), 6),
    )


async def parse_natural_language_query(
    db: AsyncSession,
    question: str,
) -> NLQueryResult:
    q = question.lower()

    now = datetime.now(UTC)
    time_map: dict[str, timedelta] = {
        "last hour": timedelta(hours=1),
        "last 1 hour": timedelta(hours=1),
        "past hour": timedelta(hours=1),
        "son 1 saat": timedelta(hours=1),
        "son saat": timedelta(hours=1),
        "son bir saat": timedelta(hours=1),
        "last 24 hours": timedelta(hours=24),
        "past 24 hours": timedelta(hours=24),
        "last 24h": timedelta(hours=24),
        "son 24 saat": timedelta(hours=24),
        "bugun": timedelta(hours=24),
        "today": timedelta(hours=24),
        "last 7 days": timedelta(days=7),
        "past 7 days": timedelta(days=7),
        "this week": timedelta(days=7),
        "bu hafta": timedelta(days=7),
        "son 7 gun": timedelta(days=7),
        "son 7 gün": timedelta(days=7),
        "last week": timedelta(days=14),
        "gecen hafta": timedelta(days=14),
        "geçen hafta": timedelta(days=14),
        "last 30 days": timedelta(days=30),
        "past month": timedelta(days=30),
        "last month": timedelta(days=60),
        "son 30 gun": timedelta(days=30),
        "son 30 gün": timedelta(days=30),
        "gecen ay": timedelta(days=60),
        "geçen ay": timedelta(days=60),
    }

    is_turkish = any(c in q for c in ["ı", "ğ", "ü", "ş", "ö", "ç", "bu", "bir"])
    _ = is_turkish  # used by caller below for answer locale

    delta = timedelta(hours=24)
    for key, val in time_map.items():
        if key in q:
            delta = val
            break

    start = (now - delta).isoformat()
    end = now.isoformat()

    aggregation = "raw"
    eng_agg = ["average", "avg", "mean", "hourly"]
    tr_agg = ["ortalama", "ort", "saatlik"]
    if any(w in q for w in eng_agg + tr_agg):
        aggregation = "hourly"
    elif any(
        w in q for w in ["daily", "per day", "each day", "gunluk", "günlük", "her gun", "her gün"]
    ):
        aggregation = "daily"

    eng_anom = ["anomaly", "anomalies", "abnormal", "outlier", "spike"]
    tr_anom = [
        "anomali",
        "anomaliler",
        "anormal",
        "aykiri",
        "aykırı",
        "sıcrama",
        "sıçrama",
        "sapma",
        "normal olmayan",
        "beklenmeyen",
    ]
    if any(w in q for w in eng_anom + tr_anom):
        tag_hints = _extract_tag_hints(q)
        results = []
        for hint in tag_hints:
            tag_ids = await resolve_tag_names(db, [hint])
            for tid in tag_ids[:3]:
                r = await db.execute(select(Tag).where(Tag.id == tid))
                tag = r.scalar_one_or_none()
                if tag:
                    anom = await detect_anomalies(db, tag.name)
                    results.append(
                        {
                            "tag": tag.name,
                            "anomaly_count": len(anom.anomalies),
                            "anomalies": [
                                {
                                    "timestamp": a.timestamp.isoformat(),
                                    "value": a.value,
                                    "type": a.anomaly_type,
                                    "severity": a.severity,
                                }
                                for a in anom.anomalies[:20]
                            ],
                        }
                    )
        answer = (
            f"{len(results)} tag'de anomali bulundu."
            if is_turkish
            else f"Found anomalies across {len(results)} tags."
        )
        return NLQueryResult(
            question=question,
            answer=answer,
            data=results,
            chart_config=None,
        )

    stat_type = "values"
    eng_max = ["max", "maximum", "peak", "highest"]
    tr_max = ["maksimum", "en yuksek", "en yüksek", "tepe", "pik"]
    eng_min = ["min", "minimum", "lowest"]
    tr_min = ["minimum", "en dusuk", "en düşük"]
    eng_cnt = ["count", "how many", "number of"]
    tr_cnt = ["kac tane", "kaç tane", "sayisi", "sayısı", "kac kez", "kaç kez"]
    eng_avg = ["average", "avg", "mean"]
    tr_avg = ["ortalama", "ortalamasi", "ortalaması"]
    if any(w in q for w in eng_max + tr_max):
        stat_type = "max"
    elif any(w in q for w in eng_min + tr_min):
        stat_type = "min"
    elif any(w in q for w in eng_cnt + tr_cnt):
        stat_type = "count"
    elif any(w in q for w in eng_avg + tr_avg):
        stat_type = "avg"

    tag_hints = _extract_tag_hints(q)

    if not tag_hints:
        answer = (
            "Hangi tag'lari sordugunuzu anlayamadim. Tag adi belirtin, ornegin 'debi' veya 'pH'."
            if is_turkish
            else (
                "I couldn't identify which tags you're asking about. "
                "Try including specific tag names like 'flow rate' or 'pH'."
            )
        )
        return NLQueryResult(
            question=question,
            answer=answer,
            data=None,
            chart_config=None,
        )

    tag_ids = await resolve_tag_names(db, tag_hints)
    if not tag_ids:
        answer = (
            f"'{', '.join(tag_hints)}' ile eslesen tag bulunamadi."
            if is_turkish
            else f"I couldn't find any tags matching '{', '.join(tag_hints)}'."
        )
        return NLQueryResult(
            question=question,
            answer=answer,
            data=None,
            chart_config=None,
        )

    r = await db.execute(select(Tag).where(Tag.id.in_(tag_ids[:5])))
    tags = r.scalars().all()

    tag_info = [{"name": t.name, "unit": t.unit, "device": t.device} for t in tags]

    answer = (
        f"{len(tags)} tag bulundu: {', '.join(t.name for t in tags)}. "
        f"Zaman: son {delta}. Toplulastirma: {aggregation}. Istatistik: {stat_type}."
        if is_turkish
        else f"Found {len(tags)} matching tags: {', '.join(t.name for t in tags)}. "
        f"Time range: {delta} ending now. Aggregation: {aggregation}. Stat: {stat_type}."
    )

    return NLQueryResult(
        question=question,
        answer=answer,
        data=tag_info,
        chart_config={
            "type": "trend",
            "tags": [t.name for t in tags],
            "start": start,
            "end": end,
            "aggregation": aggregation,
            "stat_type": stat_type,
        },
    )


async def generate_ai_report(
    db: AsyncSession,
    tags: list[str],
    start: str,
    end: str,
    report_format: str = "excel",
    aggregation: str = "raw",
) -> dict[str, Any]:
    """Generate a report with AI-powered summary."""
    tag_ids = await resolve_tag_names(db, tags)
    if not tag_ids:
        return {"error": "No matching tags found", "tags_queried": tags}

    r = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
    tag_objects = r.scalars().all()

    # Fetch data summary
    summary = []
    for tid in tag_objects:
        rows = await db.execute(
            select(
                func.count(TagReading.value),
                func.avg(TagReading.value),
                func.min(TagReading.value),
                func.max(TagReading.value),
            ).where(
                TagReading.tag_id == tid.id,
                TagReading.timestamp >= start,
                TagReading.timestamp <= end,
            )
        )
        count, avg, mn, mx = rows.one()
        summary.append(
            {
                "tag": tid.name,
                "unit": tid.unit,
                "readings": count,
                "average": round(float(avg), 2) if avg else None,
                "minimum": round(float(mn), 2) if mn else None,
                "maximum": round(float(mx), 2) if mx else None,
            }
        )

    return {
        "tags_analyzed": len(summary),
        "summary": summary,
        "time_range": {"start": start, "end": end},
        "format": report_format,
        "aggregation": aggregation,
    }


async def get_system_health(db: AsyncSession) -> dict[str, Any]:
    tag_count = await db.scalar(select(func.count(Tag.id)))
    active_count = await db.scalar(select(func.count(Tag.id)).where(Tag.is_active))
    return {
        "tags": {"total": tag_count, "active": active_count},
        "ai_services": ["anomaly_detection", "trend_prediction", "nl_query", "auto_report"],
        "mcp_servers": ["scada", "scada-db"],
    }


def _parse_window(window: str) -> int:
    window = window.lower().strip()
    if window.endswith("h"):
        return int(window[:-1]) * 3600
    if window.endswith("d"):
        return int(window[:-1]) * 86400
    if window.endswith("m"):
        return int(window[:-1]) * 60
    if window.endswith("s"):
        return int(window[:-1])
    return 86400


def _extract_tag_hints(question: str) -> list[str]:
    """Extract likely tag names from a natural language question using heuristics."""
    stop_words = {
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "and",
        "or",
        "what",
        "was",
        "were",
        "is",
        "are",
        "show",
        "give",
        "me",
        "last",
        "past",
        "hour",
        "hours",
        "days",
        "today",
        "yesterday",
        "this",
        "week",
        "month",
        "average",
        "minimum",
        "maximum",
        "count",
        "value",
        "values",
        "reading",
        "readings",
        "data",
        "trend",
        "chart",
        "graph",
        "plot",
        "from",
        "between",
        "please",
        "can",
        "you",
        "how",
        "many",
        "does",
        # Turkish
        "bir",
        "bu",
        "su",
        "şu",
        "o",
        "ve",
        "ile",
        "icin",
        "için",
        "ama",
        "fakat",
        "veya",
        "degil",
        "değil",
        "var",
        "yok",
        "mi",
        "mu",
        "mı",
        "da",
        "de",
        "den",
        "dan",
        "ten",
        "tan",
        "nin",
        "nın",
        "bana",
        "sana",
        "bize",
        "size",
        "ben",
        "sen",
        "biz",
        "siz",
        "onlar",
        "ne",
        "nasil",
        "nasıl",
        "neden",
        "nicin",
        "niçin",
        "kim",
        "hangi",
        "goster",
        "göster",
        "ver",
        "kac",
        "kaç",
        "tane",
        "adet",
        "son",
        "gecen",
        "geçen",
        "saat",
        "saatlik",
        "gun",
        "gün",
        "gunluk",
        "günlük",
        "hafta",
        "haftalik",
        "haftalık",
        "ay",
        "aylik",
        "aylık",
        "ortalama",
        "maksimum",
        "toplam",
        "deger",
        "değer",
        "degerler",
        "değerler",
        "okuma",
        "okumalar",
        "veri",
        "egilim",
        "eğilim",
        "grafik",
        "tablo",
        "cizelge",
        "çizelge",
        "cizgi",
        "çizgi",
        "lütfen",
        "lutfen",
        "yap",
        "misin",
        "musun",
        "mısın",
    }
    words = question.lower().split()

    # Group consecutive non-stop words as multi-word tag names
    grouped: list[str] = []
    current: list[str] = []
    for w in words:
        if w in stop_words or len(w) <= 2:
            if current:
                grouped.append(" ".join(current))
                current = []
        else:
            current.append(w)
    if current:
        grouped.append(" ".join(current))

    return grouped
