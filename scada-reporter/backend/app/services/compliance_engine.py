from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import as_utc
from app.models.compliance import (
    ComplianceDischargePoint,
    ComplianceEvent,
    ComplianceEventNote,
    ComplianceLimit,
    ComplianceParameter,
    CompliancePermit,
)
from app.models.lab import LabMeasurement, LabSample
from app.models.tag import TagReading


def _naive_utc(dt: datetime) -> datetime:
    norm = as_utc(dt)
    if norm is None:
        raise ValueError("datetime is required")
    return norm.replace(tzinfo=None)


def build_event_key(
    permit_id: int,
    parameter_id: int,
    limit_id: int,
    event_type: str,
    period_start: datetime,
    period_end: datetime,
) -> str:
    payload = "|".join(
        [
            str(permit_id),
            str(parameter_id),
            str(limit_id),
            event_type,
            _naive_utc(period_start).isoformat(timespec="seconds"),
            _naive_utc(period_end).isoformat(timespec="seconds"),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compact_json(data: dict) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True, default=str)


async def _upsert_event(
    db: AsyncSession,
    *,
    permit_id: int,
    parameter_id: int,
    limit_id: int,
    event_type: str,
    period_start: datetime,
    period_end: datetime,
    status: str,
    severity: str = "warning",
    observed_value: float | None = None,
    limit_value: float | None = None,
    evidence: dict | None = None,
    acknowledged_at: datetime | None = None,
    resolved_at: datetime | None = None,
    waived_at: datetime | None = None,
    waive_reason: str | None = None,
) -> tuple[ComplianceEvent, bool]:
    event_key = build_event_key(
        permit_id, parameter_id, limit_id, event_type, period_start, period_end
    )
    result = await db.execute(select(ComplianceEvent).where(ComplianceEvent.event_key == event_key))
    event = result.scalar_one_or_none()
    created = event is None
    if event is None:
        event = ComplianceEvent(
            permit_id=permit_id,
            parameter_id=parameter_id,
            limit_id=limit_id,
            event_type=event_type,
            period_start=_naive_utc(period_start),
            period_end=_naive_utc(period_end),
            event_key=event_key,
        )
        db.add(event)

    event.severity = severity
    event.status = status
    event.observed_value = observed_value
    event.limit_value = limit_value
    event.evidence_json = _compact_json(evidence or {})
    event.acknowledged_at = acknowledged_at
    event.resolved_at = resolved_at if status == "resolved" else None
    event.waived_at = waived_at
    event.waive_reason = waive_reason

    return event, created


def _reading_rows(readings: list[tuple[datetime, float | None, int]]) -> dict[str, object]:
    values = [value for _ts, value, quality in readings if quality >= 192 and value is not None]
    bad = [value for _ts, value, quality in readings if quality < 192 or value is None]
    return {
        "count": len(readings),
        "good_count": len(values),
        "bad_count": len(bad),
        "values": values,
        "bad_values": bad,
    }


async def _fetch_scada_readings(
    db: AsyncSession,
    *,
    tag_id: int,
    period_start: datetime,
    period_end: datetime,
) -> list[tuple[datetime, float | None, int]]:
    result = await db.execute(
        select(TagReading.timestamp, TagReading.value, TagReading.quality)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= _naive_utc(period_start),
            TagReading.timestamp < _naive_utc(period_end),
        )
        .order_by(TagReading.timestamp.asc())
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


async def _fetch_lab_measurements(
    db: AsyncSession,
    *,
    sample_point_id: int,
    lab_parameter_id: int,
    period_start: datetime,
    period_end: datetime,
) -> list[tuple[datetime, float | None]]:
    result = await db.execute(
        select(LabSample.sampled_at, LabMeasurement.value)
        .join(LabMeasurement, LabMeasurement.sample_id == LabSample.id)
        .where(
            LabSample.sample_point_id == sample_point_id,
            LabMeasurement.parameter_id == lab_parameter_id,
            LabSample.sampled_at >= _naive_utc(period_start),
            LabSample.sampled_at < _naive_utc(period_end),
        )
        .order_by(LabSample.sampled_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


def _sample_threshold(limit: ComplianceLimit) -> float:
    if limit.min_value is not None:
        return float(limit.min_value)
    if limit.max_value is not None:
        return float(limit.max_value)
    return 1.0


def _quality_threshold(limit: ComplianceLimit) -> int:
    if limit.max_value is not None:
        return int(limit.max_value)
    return 192


def _value_limit_violation(
    values: list[float], limit: ComplianceLimit
) -> tuple[bool, float | None]:
    if not values:
        return False, None

    observed: float | None = None
    if limit.max_value is not None:
        observed = max(values)
        if observed > limit.max_value:
            return True, observed
    if limit.min_value is not None:
        observed = min(values)
        if observed < limit.min_value:
            return True, observed
    return False, observed


async def _source_event_count_notes(db: AsyncSession, event_id: int) -> int:
    result = await db.execute(
        select(func.count(ComplianceEventNote.id)).where(ComplianceEventNote.event_id == event_id)
    )
    return int(result.scalar_one())


async def evaluate_permit(
    db: AsyncSession,
    permit_id: int,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, int]:
    start = _naive_utc(period_start)
    end = _naive_utc(period_end)
    result = await db.execute(select(CompliancePermit).where(CompliancePermit.id == permit_id))
    permit = result.scalar_one_or_none()
    if permit is None:
        return {"created": 0, "updated": 0, "resolved": 0}

    result = await db.execute(
        select(ComplianceParameter, ComplianceLimit)
        .join(ComplianceLimit, ComplianceLimit.compliance_parameter_id == ComplianceParameter.id)
        .where(ComplianceParameter.permit_id == permit_id)
        .order_by(ComplianceParameter.id.asc(), ComplianceLimit.id.asc())
    )
    rows = result.all()

    counters = {"created": 0, "updated": 0, "resolved": 0}

    for parameter, limit in rows:
        source_type = parameter.source_type
        limit_bound = limit.max_value if limit.max_value is not None else limit.min_value
        evidence: dict[str, object] = {
            "source": {
                "permit_id": permit_id,
                "parameter_id": parameter.id,
                "limit_id": limit.id,
                "source_type": source_type,
                "limit_type": limit.limit_type,
                "aggregation": limit.aggregation,
            }
        }

        source_event_type = "limit_exceeded"
        status = "resolved"
        severity = limit.severity or "warning"
        observed_value: float | None = None
        limit_value: float | None = None

        scada_rows: list[tuple[datetime, float | None, int]] = []
        lab_rows: list[tuple[datetime, float | None]] = []
        sample_count = 0

        if source_type in {"scada", "hybrid"} and parameter.tag_id is not None:
            scada_rows = await _fetch_scada_readings(
                db, tag_id=parameter.tag_id, period_start=start, period_end=end
            )
            evidence["scada"] = _reading_rows(scada_rows)

        if source_type in {"lab", "hybrid"}:
            point = (
                await db.execute(
                    select(ComplianceDischargePoint.lab_sample_point_id).where(
                        ComplianceDischargePoint.id == parameter.discharge_point_id
                    )
                )
            ).scalar_one_or_none()
            if point is not None and parameter.lab_parameter_id is not None:
                lab_rows = await _fetch_lab_measurements(
                    db,
                    sample_point_id=int(point),
                    lab_parameter_id=parameter.lab_parameter_id,
                    period_start=start,
                    period_end=end,
                )
            sample_count = len(lab_rows)
            evidence["lab"] = {
                "count": sample_count,
                "values": [value for _ts, value in lab_rows if value is not None],
            }

        if limit.limit_type == "sample_count":
            required = _sample_threshold(limit)
            observed_count = (
                sample_count
                if source_type in {"lab", "hybrid"}
                else len([row for row in scada_rows if row[2] >= 192 and row[1] is not None])
            )
            evidence["rule"] = {
                "event_type": "missing_sample" if observed_count < required else "sample_count_ok",
                "required": required,
                "observed": observed_count,
            }
            if observed_count < required:
                source_event_type = "missing_sample"
                status = "open"
                limit_value = required
                if source_type == "hybrid" and scada_rows:
                    evidence["provisional_scada"] = {
                        "count": len(scada_rows),
                        "values": [
                            value
                            for _ts, value, quality in scada_rows
                            if quality >= 192 and value is not None
                        ],
                    }
            else:
                source_event_type = "missing_sample"
                status = "resolved"
                limit_value = required
                observed_value = float(observed_count)

        elif limit.limit_type == "quality":
            threshold = _quality_threshold(limit)
            bad_readings = [row for row in scada_rows if row[2] < threshold or row[1] is None]
            evidence["rule"] = {
                "event_type": "bad_quality" if bad_readings else "quality_ok",
                "threshold": threshold,
                "bad_count": len(bad_readings),
            }
            if bad_readings:
                source_event_type = "bad_quality"
                status = "open"
                observed_value = float(min(row[2] for row in bad_readings))
                limit_value = float(threshold)
            else:
                source_event_type = "bad_quality"
                status = "resolved"
                limit_value = float(threshold)

        elif limit.limit_type == "value_limit":
            evidence["rule"] = {
                "event_type": "limit_exceeded",
                "min_value": limit.min_value,
                "max_value": limit.max_value,
            }
            if source_type == "scada":
                values = [
                    value
                    for _ts, value, quality in scada_rows
                    if quality >= 192 and value is not None
                ]
                violated, observed = _value_limit_violation(values, limit)
                if violated:
                    status = "open"
                    observed_value = observed
                    limit_value = limit_bound
                else:
                    status = "resolved"
                    observed_value = max(values) if values else None
                    limit_value = limit_bound
            else:
                lab_values = [value for _ts, value in lab_rows if value is not None]
                if lab_values:
                    violated, observed = _value_limit_violation(lab_values, limit)
                    if violated:
                        status = "open"
                        observed_value = observed
                        limit_value = limit_bound
                    else:
                        status = "resolved"
                        observed_value = max(lab_values)
                        limit_value = limit_bound
                else:
                    source_event_type = "missing_sample"
                    status = "open"
                    limit_value = limit_bound
                    evidence["provisional_scada"] = {
                        "count": len(scada_rows),
                        "values": [
                            value
                            for _ts, value, quality in scada_rows
                            if quality >= 192 and value is not None
                        ],
                    }

        source_event, created = await _upsert_event(
            db,
            permit_id=permit_id,
            parameter_id=parameter.id,
            limit_id=limit.id,
            event_type=source_event_type,
            period_start=start,
            period_end=end,
            status=status,
            severity=severity,
            observed_value=observed_value,
            limit_value=limit_value,
            evidence=evidence,
        )
        counters["created" if created else "updated"] += 1
        if source_event.status == "resolved":
            counters["resolved"] += 1

        await db.flush()

        if limit.requires_explanation:
            note_count = await _source_event_count_notes(db, source_event.id)
            explanation_status = "open"
            if source_event.status != "open" or note_count > 0:
                explanation_status = "resolved"
            explanation_event, explanation_created = await _upsert_event(
                db,
                permit_id=permit_id,
                parameter_id=parameter.id,
                limit_id=limit.id,
                event_type="needs_explanation",
                period_start=start,
                period_end=end,
                status=explanation_status,
                severity=severity,
                observed_value=observed_value,
                limit_value=limit_value,
                evidence={
                    "source_event_key": source_event.event_key,
                    "source_event_type": source_event.event_type,
                    "note_count": note_count,
                    "requires_explanation": True,
                },
                resolved_at=datetime.now(UTC) if explanation_status == "resolved" else None,
            )
            counters["created" if explanation_created else "updated"] += 1
            if explanation_event.status == "resolved":
                counters["resolved"] += 1

    await db.flush()
    return counters
