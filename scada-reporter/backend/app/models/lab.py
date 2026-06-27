from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LabParameter(Base):
    __tablename__ = "lab_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    min_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    # Hybrid catalog: operator-added entries land approved=False, awaiting admin.
    approved: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    # Optional mirror into tag_readings for same-panel SCADA comparison + reports.
    mirror_to_tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )


class LabSamplePoint(Base):
    __tablename__ = "lab_sample_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    approved: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)


class LabSample(Base):
    __tablename__ = "lab_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_sample_points.id"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    entered_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(255), default="")
    batch_no: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    measurements: Mapped[list[LabMeasurement]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class LabMeasurement(Base):
    __tablename__ = "lab_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_samples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parameter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lab_parameters.id"), nullable=False, index=True
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    sample: Mapped[LabSample] = relationship(back_populates="measurements")
