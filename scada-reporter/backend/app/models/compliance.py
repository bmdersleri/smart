"""Compliance Center ORM models.

Permit-driven compliance domain: permits, discharge points, monitored
parameters, limit/sampling rules, durable compliance events, and operator
explanation notes.

These records are legal/regulatory artifacts: Phase-1 uses explicit RESTRICT
semantics — relationships are defined for navigation only and intentionally
do NOT cascade-delete (we never silently drop compliance events or notes when
a parent permit/point/parameter/limit is removed).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.lab import LabParameter, LabSamplePoint
from app.models.tag import Tag
from app.models.user import User

# --- Allowed value vocabularies (validated at the API layer) --------------

REPORT_FREQUENCIES = ("daily", "weekly", "monthly", "quarterly", "custom_cron")
SOURCE_TYPES = ("scada", "lab", "hybrid")
LIMIT_TYPES = ("value_limit", "sample_count", "sample_frequency", "quality")
AGGREGATIONS = ("instant", "daily_avg", "monthly_avg", "count")
EVENT_TYPES = (
    "limit_exceeded",
    "missing_sample",
    "late_sample",
    "bad_quality",
    "needs_explanation",
)
EVENT_STATUSES = ("open", "acknowledged", "resolved", "waived")
REPORT_PACK_STATUSES = ("draft", "ready_for_review", "failed", "approved", "exported")


class CompliancePermit(Base):
    __tablename__ = "compliance_permits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    facility_name: Mapped[str] = mapped_column(String(255), default="")
    authority: Mapped[str] = mapped_column(String(255), default="")
    permit_number: Mapped[str] = mapped_column(String(128), default="")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    report_frequency: Mapped[str] = mapped_column(String(32), default="monthly")
    report_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    discharge_points: Mapped[list[ComplianceDischargePoint]] = relationship(back_populates="permit")
    parameters: Mapped[list[ComplianceParameter]] = relationship(back_populates="permit")


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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    permit: Mapped[CompliancePermit] = relationship(back_populates="discharge_points")
    lab_sample_point: Mapped[LabSamplePoint | None] = relationship()
    parameters: Mapped[list[ComplianceParameter]] = relationship(back_populates="discharge_point")


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
    unit: Mapped[str] = mapped_column(String(64), default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tag_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tags.id"), nullable=True)
    lab_parameter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lab_parameters.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    permit: Mapped[CompliancePermit] = relationship(back_populates="parameters")
    discharge_point: Mapped[ComplianceDischargePoint] = relationship(back_populates="parameters")
    tag: Mapped[Tag | None] = relationship()
    lab_parameter: Mapped[LabParameter | None] = relationship()
    limits: Mapped[list[ComplianceLimit]] = relationship(back_populates="parameter")


class ComplianceLimit(Base):
    __tablename__ = "compliance_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_parameters.id"), nullable=False, index=True
    )
    limit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregation: Mapped[str] = mapped_column(String(32), nullable=False)
    window: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    requires_explanation: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

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
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
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
    notes: Mapped[list[ComplianceEventNote]] = relationship(back_populates="event")


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


class ComplianceReportPack(Base):
    """Period-level official compliance report package.

    A legal/regulatory artifact: like the other compliance models it does NOT
    cascade-delete. The generated PDF/Excel/JSON outputs are stored as blobs on
    the row; ``events_snapshot_json`` is frozen on approval (evidence
    immutability). ``archive_id`` is reserved for future ``report_archive``
    linkage and is NOT used in Phase 3.
    """

    __tablename__ = "compliance_report_packs"
    __table_args__ = (
        Index("ix_compliance_report_packs_permit_period", "permit_id", "period_start"),
        Index("ix_compliance_report_packs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    events_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("report_archive.id"), nullable=True
    )
    pdf_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    xlsx_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    json_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    permit: Mapped[CompliancePermit] = relationship()


__all__ = [
    "AGGREGATIONS",
    "EVENT_STATUSES",
    "EVENT_TYPES",
    "LIMIT_TYPES",
    "REPORT_FREQUENCIES",
    "REPORT_PACK_STATUSES",
    "SOURCE_TYPES",
    "ComplianceDischargePoint",
    "ComplianceEvent",
    "ComplianceEventNote",
    "ComplianceLimit",
    "ComplianceParameter",
    "CompliancePermit",
    "ComplianceReportPack",
]
