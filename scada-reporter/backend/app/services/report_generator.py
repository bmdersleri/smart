import gzip
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_archive import ReportArchive
from app.models.tag import Tag, TagReading
from app.services.chart_generator import generate_summary_bar_chart, generate_timeseries_chart
from app.services.excel_builder import build_advanced_excel
from app.services.pdf_builder import build_pdf
from app.services.stats_engine import compute_tag_stats, detect_anomalies


def resolve_time_range(template) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    mapping = {
        "last_1h": (now - timedelta(hours=1), now),
        "last_24h": (now - timedelta(hours=24), now),
        "last_7d": (now - timedelta(days=7), now),
        "last_30d": (now - timedelta(days=30), now),
        "custom": (template.custom_start, template.custom_end),
    }
    return mapping[template.time_range_type]


def _aggregate_periods(
    rows: list[tuple[datetime, float | None, int]],
    interval: str,
) -> list[dict]:
    freq = {"hourly": "h", "daily": "D", "weekly": "W"}[interval]
    data = [(t, v) for t, v, q in rows if v is not None and q == 192]
    if not data:
        return []
    df = pd.DataFrame(data, columns=["timestamp", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    g = df["value"].resample(freq).agg(["mean", "min", "max", "count"]).dropna()
    return [
        {
            "period": idx.isoformat(),
            "mean": round(float(r["mean"]), 3),
            "min": round(float(r["min"]), 3),
            "max": round(float(r["max"]), 3),
            "count": int(r["count"]),
        }
        for idx, r in g.iterrows()
    ]


async def generate_report_from_template(
    template,
    start: datetime,
    end: datetime,
    db: AsyncSession,
    archive_id: int,
) -> ReportArchive:
    archive = await db.get(ReportArchive, archive_id)
    if archive is None:
        raise ValueError(f"ReportArchive {archive_id} not found")

    archive.status = "running"
    archive.started_at = datetime.now(UTC)
    await db.commit()

    try:
        tag_ids: list[int] = json.loads(template.tag_ids)
        percentile_levels: list[int] = json.loads(template.percentile_levels)

        tag_rows = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        tags = {t.id: t for t in tag_rows.scalars().all()}

        per_tag_data: list[dict] = []

        for tag_id in tag_ids:
            tag = tags.get(tag_id)
            if tag is None:
                continue

            result = await db.execute(
                select(TagReading.timestamp, TagReading.value, TagReading.quality)
                .where(
                    TagReading.tag_id == tag_id,
                    TagReading.timestamp >= start,
                    TagReading.timestamp <= end,
                )
                .order_by(TagReading.timestamp)
            )
            raw = result.all()
            rows: list[tuple[datetime, float | None, int]] = [(r[0], r[1], r[2]) for r in raw]

            stats = compute_tag_stats(
                rows,
                tag.id,
                tag.name,
                tag.unit or "",
                percentile_levels,
                expected_interval_seconds=5,
            )

            anomalies = []
            if template.anomaly_enabled:
                anomalies = detect_anomalies(
                    rows,
                    stats,
                    template.anomaly_zscore_threshold,
                    tag.min_alarm,
                    tag.max_alarm,
                )

            chart_png = b""
            if template.show_trend_charts:
                anom_ts = [e.timestamp for e in anomalies]
                chart_png = generate_timeseries_chart(
                    [r[0] for r in rows],
                    [r[1] for r in rows],
                    anom_ts,
                    tag.name,
                    tag.unit or "",
                )

            period_rows = _aggregate_periods(rows, template.interval)

            per_tag_data.append(
                {
                    "tag": tag,
                    "stats": stats,
                    "anomalies": anomalies,
                    "period_rows": period_rows,
                    "chart_png": chart_png,
                    "raw_readings": rows,
                }
            )

        # Summary bar chart
        avgs = [td["stats"].avg or 0.0 for td in per_tag_data]
        names = [td["tag"].name for td in per_tag_data]
        units = per_tag_data[0]["tag"].unit or "" if per_tag_data else ""
        summary_chart = generate_summary_bar_chart(names, avgs, units) if per_tag_data else b""

        # Build output
        os.makedirs("reports", exist_ok=True)
        uid = f"{archive_id}_{int(datetime.now(UTC).timestamp())}"

        if template.output_format == "excel":
            content = build_advanced_excel(archive, per_tag_data, template, summary_chart)
            ext = "xlsx"
        elif template.output_format == "pdf":
            from app.core.config import settings

            generated_at = datetime.now(UTC)
            content = build_pdf(
                archive, per_tag_data, template, settings.FACILITY_NAME, generated_at
            )
            ext = "pdf"
        else:
            # JSON
            serialized = {
                "archive_id": archive_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "tags": [
                    {
                        "tag_id": td["tag"].id,
                        "tag_name": td["tag"].name,
                        "stats": asdict(td["stats"]),
                        "anomaly_count": len(td["anomalies"]),
                        "period_rows": td["period_rows"],
                    }
                    for td in per_tag_data
                ],
            }
            content = json.dumps(serialized, default=str).encode()
            ext = "json"

        file_path = f"reports/{uid}.{ext}"
        with open(file_path, "wb") as f:
            f.write(content)

        # Compressed summary for DB
        summary = {
            "tags": [
                {
                    "name": td["tag"].name,
                    "stats": asdict(td["stats"]),
                    "anomaly_count": len(td["anomalies"]),
                }
                for td in per_tag_data
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        archive.result_json = gzip.compress(json.dumps(summary, default=str).encode())
        archive.file_path = file_path
        archive.file_size_bytes = len(content)
        archive.status = "completed"
        archive.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(archive)

    except Exception as exc:
        archive.status = "failed"
        archive.error_message = str(exc)
        await db.commit()
        raise

    return archive
