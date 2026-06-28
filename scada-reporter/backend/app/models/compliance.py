from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

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
    report_cron: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    discharge_points: Mapped[list[ComplianceDischargePoint]] = relationship(
        back_populates="permit", passive_deletes=True
    )
    parameters: Mapped[list[ComplianceParameter]] = relationship(
        back_populates="permit",
        foreign_keys="ComplianceParameter.permit_id",
        passive_deletes=True,
    )
    events: Mapped[list[ComplianceEvent]] = relationship(
        back_populates="permit",
        foreign_keys="ComplianceEvent.permit_id",
        passive_deletes=True,
    )


class ComplianceDischargePoint(Base):
    __tablename__ = "compliance_discharge_points"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "permit_id",
            name="uq_compliance_discharge_points_id_permit_id",
        ),
    )

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
    parameters: Mapped[list[ComplianceParameter]] = relationship(
        back_populates="discharge_point",
        foreign_keys="(ComplianceParameter.discharge_point_id, ComplianceParameter.permit_id)",
        overlaps="parameters",
        passive_deletes=True,
    )


class ComplianceParameter(Base):
    __tablename__ = "compliance_parameters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["discharge_point_id", "permit_id"],
            ["compliance_discharge_points.id", "compliance_discharge_points.permit_id"],
            name="fk_compliance_parameters_discharge_point_permit",
        ),
        UniqueConstraint("id", "permit_id", name="uq_compliance_parameters_id_permit_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False, index=True
    )
    discharge_point_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tag_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tags.id"), nullable=True)
    lab_parameter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lab_parameters.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    permit: Mapped[CompliancePermit] = relationship(
        back_populates="parameters",
        foreign_keys=[permit_id],
        overlaps="parameters",
    )
    discharge_point: Mapped[ComplianceDischargePoint] = relationship(
        back_populates="parameters",
        foreign_keys=[discharge_point_id, permit_id],
        overlaps="parameters,permit",
    )
    limits: Mapped[list[ComplianceLimit]] = relationship(
        back_populates="parameter", passive_deletes=True
    )
    events: Mapped[list[ComplianceEvent]] = relationship(
        back_populates="parameter",
        foreign_keys="(ComplianceEvent.parameter_id, ComplianceEvent.permit_id)",
        overlaps="events",
        passive_deletes=True,
    )


class ComplianceLimit(Base):
    __tablename__ = "compliance_limits"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "compliance_parameter_id",
            name="uq_compliance_limits_id_parameter_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compliance_parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_parameters.id"), nullable=False, index=True
    )
    limit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregation: Mapped[str] = mapped_column(String(32), default="instant")
    window: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    requires_explanation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    parameter: Mapped[ComplianceParameter] = relationship(back_populates="limits")
    events: Mapped[list[ComplianceEvent]] = relationship(
        back_populates="limit",
        foreign_keys="(ComplianceEvent.limit_id, ComplianceEvent.parameter_id)",
        overlaps="events",
        passive_deletes=True,
    )


class ComplianceEvent(Base):
    __tablename__ = "compliance_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["parameter_id", "permit_id"],
            ["compliance_parameters.id", "compliance_parameters.permit_id"],
            name="fk_compliance_events_parameter_permit",
        ),
        ForeignKeyConstraint(
            ["limit_id", "parameter_id"],
            ["compliance_limits.id", "compliance_limits.compliance_parameter_id"],
            name="fk_compliance_events_limit_parameter",
        ),
        UniqueConstraint("event_key", name="uq_compliance_events_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_permits.id"), nullable=False, index=True
    )
    parameter_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    limit_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
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
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    waived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    waived_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    waive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    permit: Mapped[CompliancePermit] = relationship(
        back_populates="events",
        foreign_keys=[permit_id],
        overlaps="events",
    )
    parameter: Mapped[ComplianceParameter] = relationship(
        back_populates="events",
        foreign_keys=[parameter_id, permit_id],
        overlaps="events,limit,permit",
    )
    limit: Mapped[ComplianceLimit] = relationship(
        back_populates="events",
        foreign_keys=[limit_id, parameter_id],
        overlaps="events,parameter",
    )
    notes: Mapped[list[ComplianceEventNote]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class ComplianceEventNote(Base):
    __tablename__ = "compliance_event_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped[ComplianceEvent] = relationship(back_populates="notes")
