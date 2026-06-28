from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.lab import LabMeasurement, LabParameter, LabSample, LabSamplePoint
from app.models.tag import Tag, TagReading
from app.models.user import User

QUALITY_GOOD = 192

EVENT_OPEN = "open"
EVENT_RESOLVED = "resolved"

EVENT_TYPE_LIMIT_EXCEEDED = "limit_exceeded"
EVENT_TYPE_MISSING_SAMPLE = "missing_sample"
EVENT_TYPE_LATE_SAMPLE = "late_sample"
EVENT_TYPE_BAD_QUALITY = "bad_quality"
EVENT_TYPE_NEEDS_EXPLANATION = "needs_explanation"


@dataclass(slots=True)
class EvaluatedEvent:
    event_type: str
    observed_value: float | None
    limit_value: float | None
    evidence: dict[str, object]


class CompliancePermit(Base):
    __tablename__ = "compliance_permits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    discharge_points: Mapped[list[ComplianceDischargePoint]] = relationship(
        back_populates="permit", cascade="all, delete-orphan"
    )
    parameters: Mapped[list[ComplianceParameter]] = relationship(
        back_populates="permit", cascade="all, delete-orphan"
    )


class ComplianceDischargePoint(Base):
    __tablename__ = "compliance_discharge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    lab_sample_point_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lab_sample_points.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    permit: Mapped[CompliancePermit] = relationship(back_populates="discharge_points")
    lab_sample_point: Mapped[LabSamplePoint | None] = relationship()
    parameters: Mapped[list[ComplianceParameter]] = relationship(
        back_populates="discharge_point", cascade="all, delete-orphan"
    )


class ComplianceParameter(Base):
    __tablename__ = "compliance_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False, index=True
    )
    discharge_point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_discharge_points.id"), nullable=False, index=True
    )
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tag_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tags.id"), nullable=True)
    lab_parameter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lab_parameters.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    permit: Mapped[CompliancePermit] = relationship(back_populates="parameters")
    discharge_point: Mapped[ComplianceDischargePoint] = relationship(back_populates="parameters")
    tag: Mapped[Tag | None] = relationship()
    lab_parameter: Mapped[LabParameter | None] = relationship()
    limits: Mapped[list[ComplianceLimit]] = relationship(
        back_populates="parameter", cascade="all, delete-orphan"
    )


class ComplianceLimit(Base):
    __tablename__ = "compliance_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_parameters.id"), nullable=False, index=True
    )
    limit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(32), nullable=False)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_explanation: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    parameter: Mapped[ComplianceParameter] = relationship(back_populates="limits")


class ComplianceEvent(Base):
    __tablename__ = "compliance_events"
    __table_args__ = (UniqueConstraint("event_key", name="uq_compliance_events_event_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False, index=True
    )
    parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_parameters.id"), nullable=False, index=True
    )
    limit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_limits.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EVENT_OPEN)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    waived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    waived_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    waive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    permit: Mapped[CompliancePermit] = relationship()
    parameter: Mapped[ComplianceParameter] = relationship()
    limit: Mapped[ComplianceLimit] = relationship()
    acknowledged_user: Mapped[User | None] = relationship(
        foreign_keys=[acknowledged_by], lazy="joined"
    )
    resolved_user: Mapped[User | None] = relationship(foreign_keys=[resolved_by], lazy="joined")
    waived_user: Mapped[User | None] = relationship(foreign_keys=[waived_by], lazy="joined")
    notes: Mapped[list[ComplianceEventNote]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class ComplianceEventNote(Base):
    __tablename__ = "compliance_event_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_events.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped[ComplianceEvent] = relationship(back_populates="notes")
    user: Mapped[User] = relationship()


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _compact_json(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _quality_threshold() -> int:
    return QUALITY_GOOD


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
            _normalize_dt(period_start).isoformat(),
            _normalize_dt(period_end).isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _load_existing_events(
    session: AsyncSession, permit_id: int, period_start: datetime, period_end: datetime
) -> dict[str, ComplianceEvent]:
    stmt = select(ComplianceEvent).where(
        ComplianceEvent.permit_id == permit_id,
        ComplianceEvent.period_start == period_start,
        ComplianceEvent.period_end == period_end,
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.event_key: row for row in rows}


async def _load_notes_count(session: AsyncSession, event_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(ComplianceEventNote)
        .where(ComplianceEventNote.event_id == event_id)
    )
    return int((await session.execute(stmt)).scalar_one())


async def _load_scada_readings(
    session: AsyncSession, tag_id: int, period_start: datetime, period_end: datetime
) -> list[TagReading]:
    stmt = (
        select(TagReading)
        .where(
            TagReading.tag_id == tag_id,
            TagReading.timestamp >= period_start,
            TagReading.timestamp < period_end,
        )
        .order_by(TagReading.timestamp.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _load_lab_measurements(
    session: AsyncSession,
    parameter: ComplianceParameter,
    period_start: datetime,
    period_end: datetime,
) -> list[LabMeasurement]:
    if parameter.lab_parameter_id is None:
        return []
    stmt = (
        select(LabMeasurement)
        .join(LabSample, LabMeasurement.sample_id == LabSample.id)
        .where(
            LabMeasurement.parameter_id == parameter.lab_parameter_id,
            LabSample.sample_point_id == parameter.discharge_point.lab_sample_point_id,
            LabSample.sampled_at >= period_start,
            LabSample.sampled_at < period_end,
        )
        .order_by(LabSample.sampled_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


def _first_violating_reading(
    readings: list[TagReading], *, limit: ComplianceLimit
) -> TagReading | None:
    if limit.limit_type == "quality":
        threshold = _quality_threshold()
        for reading in readings:
            if reading.quality is not None and reading.quality < threshold:
                return reading
        return None

    for reading in readings:
        if reading.value is None:
            continue
        if limit.max_value is not None and reading.value > limit.max_value:
            return reading
        if limit.min_value is not None and reading.value < limit.min_value:
            return reading
    return None


def _build_evidence(
    *,
    parameter: ComplianceParameter,
    limit: ComplianceLimit,
    event_type: str,
    observed_value: float | None,
    limit_value: float | None,
    period_start: datetime,
    period_end: datetime,
    scada_readings: list[TagReading] | None = None,
    lab_measurements: list[LabMeasurement] | None = None,
    provisional_scada: dict | None = None,
    source_event_key: str | None = None,
    note_count: int | None = None,
) -> dict:
    payload: dict = {
        "event_type": event_type,
        "parameter": parameter.parameter_name,
        "source_type": parameter.source_type,
        "limit_type": limit.limit_type,
        "aggregation": limit.aggregation,
        "period_start": _normalize_dt(period_start).isoformat(),
        "period_end": _normalize_dt(period_end).isoformat(),
        "observed_value": observed_value,
        "limit_value": limit_value,
    }
    if scada_readings is not None:
        payload["scada_readings"] = [
            {
                "timestamp": _normalize_dt(reading.timestamp).isoformat(),
                "value": reading.value,
                "quality": reading.quality,
            }
            for reading in scada_readings
        ]
    if lab_measurements is not None:
        payload["lab_measurements"] = [
            {
                "sample_id": measurement.sample_id,
                "value": measurement.value,
                "text_value": measurement.text_value,
                "flag": measurement.flag,
            }
            for measurement in lab_measurements
        ]
    if provisional_scada is not None:
        payload["provisional_scada"] = provisional_scada
    if source_event_key is not None:
        payload["source_event_key"] = source_event_key
    if note_count is not None:
        payload["note_count"] = note_count
    return payload


async def _upsert_event(
    session: AsyncSession,
    existing_events: dict[str, ComplianceEvent],
    *,
    permit_id: int,
    parameter_id: int,
    limit_id: int,
    event_type: str,
    severity: str,
    period_start: datetime,
    period_end: datetime,
    observed_value: float | None,
    limit_value: float | None,
    evidence: dict,
    now: datetime,
    result: dict[str, int],
) -> ComplianceEvent:
    event_key = build_event_key(
        permit_id, parameter_id, limit_id, event_type, period_start, period_end
    )
    event = existing_events.get(event_key)
    if event is None:
        event = ComplianceEvent(
            permit_id=permit_id,
            parameter_id=parameter_id,
            limit_id=limit_id,
            event_type=event_type,
            severity=severity,
            period_start=period_start,
            period_end=period_end,
            observed_value=observed_value,
            limit_value=limit_value,
            status=EVENT_OPEN,
            event_key=event_key,
            evidence_json=_compact_json(evidence),
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        existing_events[event_key] = event
        result["created"] += 1
    else:
        event.permit_id = permit_id
        event.parameter_id = parameter_id
        event.limit_id = limit_id
        event.event_type = event_type
        event.severity = severity
        event.period_start = period_start
        event.period_end = period_end
        event.observed_value = observed_value
        event.limit_value = limit_value
        event.evidence_json = _compact_json(evidence)
        event.updated_at = now
        if event.status == EVENT_RESOLVED:
            event.status = EVENT_OPEN
            event.resolved_at = None
            event.resolved_by = None
        result["updated"] += 1
    return event


async def _resolve_event(event: ComplianceEvent, now: datetime, result: dict[str, int]) -> None:
    if event.status != EVENT_RESOLVED:
        event.status = EVENT_RESOLVED
        event.resolved_at = now
        event.updated_at = now
        result["updated"] += 1


async def evaluate_permit(
    session: AsyncSession, permit_id: int, period_start: datetime, period_end: datetime
) -> dict[str, int]:
    period_start = _normalize_dt(period_start)
    period_end = _normalize_dt(period_end)
    now = datetime.utcnow()
    result = {"created": 0, "updated": 0}

    existing_events = await _load_existing_events(session, permit_id, period_start, period_end)
    active_keys: set[str] = set()
    explanation_sources: list[tuple[ComplianceEvent, ComplianceLimit, ComplianceParameter]] = []

    parameter_stmt = select(ComplianceParameter).where(ComplianceParameter.permit_id == permit_id)
    parameters = list((await session.execute(parameter_stmt)).scalars().all())

    for parameter in parameters:
        limits = list(
            (
                await session.execute(
                    select(ComplianceLimit).where(ComplianceLimit.parameter_id == parameter.id)
                )
            )
            .scalars()
            .all()
        )
        scada_readings = (
            await _load_scada_readings(session, parameter.tag_id, period_start, period_end)
            if parameter.tag_id is not None
            else []
        )
        lab_measurements = await _load_lab_measurements(
            session, parameter, period_start, period_end
        )

        for limit in limits:
            if limit.limit_type == "value_limit":
                source_event = None
                observed_value = None
                limit_value = limit.max_value
                violating_scada = _first_violating_reading(scada_readings, limit=limit)

                if parameter.source_type == "lab":
                    if lab_measurements:
                        measurement = lab_measurements[0]
                        observed_value = measurement.value
                        if observed_value is not None and (
                            (limit.max_value is not None and observed_value > limit.max_value)
                            or (limit.min_value is not None and observed_value < limit.min_value)
                        ):
                            source_event = EvaluatedEvent(
                                event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                                observed_value=observed_value,
                                limit_value=limit_value,
                                evidence=_build_evidence(
                                    parameter=parameter,
                                    limit=limit,
                                    event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                                    observed_value=observed_value,
                                    limit_value=limit_value,
                                    period_start=period_start,
                                    period_end=period_end,
                                    lab_measurements=lab_measurements,
                                ),
                            )
                    else:
                        source_event = EvaluatedEvent(
                            event_type=EVENT_TYPE_MISSING_SAMPLE,
                            observed_value=0,
                            limit_value=limit.max_value,
                            evidence=_build_evidence(
                                parameter=parameter,
                                limit=limit,
                                event_type=EVENT_TYPE_MISSING_SAMPLE,
                                observed_value=0,
                                limit_value=limit.max_value,
                                period_start=period_start,
                                period_end=period_end,
                                lab_measurements=[],
                                provisional_scada={
                                    "value": scada_readings[-1].value if scada_readings else None,
                                    "quality": scada_readings[-1].quality
                                    if scada_readings
                                    else None,
                                    "timestamp": _normalize_dt(
                                        scada_readings[-1].timestamp
                                    ).isoformat()
                                    if scada_readings
                                    else None,
                                },
                            ),
                        )
                        observed_value = 0

                elif parameter.source_type == "hybrid":
                    if lab_measurements:
                        measurement = lab_measurements[0]
                        observed_value = measurement.value
                        if observed_value is not None and (
                            (limit.max_value is not None and observed_value > limit.max_value)
                            or (limit.min_value is not None and observed_value < limit.min_value)
                        ):
                            source_event = EvaluatedEvent(
                                event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                                observed_value=observed_value,
                                limit_value=limit_value,
                                evidence=_build_evidence(
                                    parameter=parameter,
                                    limit=limit,
                                    event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                                    observed_value=observed_value,
                                    limit_value=limit_value,
                                    period_start=period_start,
                                    period_end=period_end,
                                    lab_measurements=lab_measurements,
                                    scada_readings=scada_readings,
                                ),
                            )
                    else:
                        source_event = EvaluatedEvent(
                            event_type=EVENT_TYPE_MISSING_SAMPLE,
                            observed_value=0,
                            limit_value=limit.max_value,
                            evidence=_build_evidence(
                                parameter=parameter,
                                limit=limit,
                                event_type=EVENT_TYPE_MISSING_SAMPLE,
                                observed_value=0,
                                limit_value=limit.max_value,
                                period_start=period_start,
                                period_end=period_end,
                                lab_measurements=[],
                                scada_readings=scada_readings,
                                provisional_scada={
                                    "value": scada_readings[-1].value if scada_readings else None,
                                    "quality": scada_readings[-1].quality
                                    if scada_readings
                                    else None,
                                    "timestamp": _normalize_dt(
                                        scada_readings[-1].timestamp
                                    ).isoformat()
                                    if scada_readings
                                    else None,
                                },
                            ),
                        )

                else:
                    if violating_scada is not None:
                        observed_value = violating_scada.value
                        source_event = EvaluatedEvent(
                            event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                            observed_value=observed_value,
                            limit_value=limit_value,
                            evidence=_build_evidence(
                                parameter=parameter,
                                limit=limit,
                                event_type=EVENT_TYPE_LIMIT_EXCEEDED,
                                observed_value=observed_value,
                                limit_value=limit_value,
                                period_start=period_start,
                                period_end=period_end,
                                scada_readings=scada_readings,
                            ),
                        )

                if source_event is not None:
                    event = await _upsert_event(
                        session,
                        existing_events,
                        permit_id=permit_id,
                        parameter_id=parameter.id,
                        limit_id=limit.id,
                        event_type=source_event.event_type,
                        severity=limit.severity,
                        period_start=period_start,
                        period_end=period_end,
                        observed_value=source_event.observed_value,
                        limit_value=source_event.limit_value,
                        evidence=source_event.evidence,
                        now=now,
                        result=result,
                    )
                    active_keys.add(event.event_key)
                    if limit.requires_explanation:
                        explanation_sources.append((event, limit, parameter))

            elif limit.limit_type == "sample_count":
                required = int(limit.max_value or limit.min_value or 0)
                actual = len(lab_measurements)
                if actual < required:
                    evidence = _build_evidence(
                        parameter=parameter,
                        limit=limit,
                        event_type=EVENT_TYPE_MISSING_SAMPLE,
                        observed_value=actual,
                        limit_value=float(required),
                        period_start=period_start,
                        period_end=period_end,
                        lab_measurements=lab_measurements,
                        scada_readings=scada_readings,
                        provisional_scada={
                            "value": scada_readings[-1].value if scada_readings else None,
                            "quality": scada_readings[-1].quality if scada_readings else None,
                            "timestamp": _normalize_dt(scada_readings[-1].timestamp).isoformat()
                            if scada_readings
                            else None,
                        }
                        if parameter.source_type == "hybrid"
                        else None,
                    )
                    event = await _upsert_event(
                        session,
                        existing_events,
                        permit_id=permit_id,
                        parameter_id=parameter.id,
                        limit_id=limit.id,
                        event_type=EVENT_TYPE_MISSING_SAMPLE,
                        severity=limit.severity,
                        period_start=period_start,
                        period_end=period_end,
                        observed_value=actual,
                        limit_value=float(required),
                        evidence=evidence,
                        now=now,
                        result=result,
                    )
                    active_keys.add(event.event_key)
                    if limit.requires_explanation:
                        explanation_sources.append((event, limit, parameter))

            elif limit.limit_type == "quality":
                bad_reading = _first_violating_reading(scada_readings, limit=limit)
                if bad_reading is not None:
                    threshold = _quality_threshold()
                    evidence = _build_evidence(
                        parameter=parameter,
                        limit=limit,
                        event_type=EVENT_TYPE_BAD_QUALITY,
                        observed_value=bad_reading.quality,
                        limit_value=threshold,
                        period_start=period_start,
                        period_end=period_end,
                        scada_readings=scada_readings,
                    )
                    event = await _upsert_event(
                        session,
                        existing_events,
                        permit_id=permit_id,
                        parameter_id=parameter.id,
                        limit_id=limit.id,
                        event_type=EVENT_TYPE_BAD_QUALITY,
                        severity=limit.severity,
                        period_start=period_start,
                        period_end=period_end,
                        observed_value=bad_reading.quality,
                        limit_value=threshold,
                        evidence=evidence,
                        now=now,
                        result=result,
                    )
                    active_keys.add(event.event_key)
                    if limit.requires_explanation:
                        explanation_sources.append((event, limit, parameter))

    await session.flush()

    for primary_event, limit, parameter in explanation_sources:
        note_count = await _load_notes_count(session, primary_event.id)
        if note_count == 0:
            needs_event = await _upsert_event(
                session,
                existing_events,
                permit_id=permit_id,
                parameter_id=parameter.id,
                limit_id=limit.id,
                event_type=EVENT_TYPE_NEEDS_EXPLANATION,
                severity=limit.severity,
                period_start=period_start,
                period_end=period_end,
                observed_value=primary_event.observed_value,
                limit_value=primary_event.limit_value,
                evidence=_build_evidence(
                    parameter=parameter,
                    limit=limit,
                    event_type=EVENT_TYPE_NEEDS_EXPLANATION,
                    observed_value=primary_event.observed_value,
                    limit_value=primary_event.limit_value,
                    period_start=period_start,
                    period_end=period_end,
                    source_event_key=primary_event.event_key,
                    note_count=note_count,
                ),
                now=now,
                result=result,
            )
            active_keys.add(needs_event.event_key)

    await session.flush()

    for event_key, event in existing_events.items():
        if event_key not in active_keys:
            await _resolve_event(event, now, result)

    await session.flush()
    return result


__all__ = [
    "ComplianceDischargePoint",
    "ComplianceEvent",
    "ComplianceEventNote",
    "ComplianceLimit",
    "ComplianceParameter",
    "CompliancePermit",
    "build_event_key",
    "evaluate_permit",
]
