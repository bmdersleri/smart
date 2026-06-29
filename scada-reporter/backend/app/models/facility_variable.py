from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FacilityVariable(Base):
    __tablename__ = "facility_variables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # scalar|series
    value_type: Mapped[str] = mapped_column(String(16), default="number")
    unit: Mapped[str] = mapped_column(String(32), default="")
    expression_json: Mapped[str] = mapped_column(Text, nullable=False)
    null_policy: Mapped[str] = mapped_column(String(12), default="skip")  # skip|zero_fill|fail
    quality_policy: Mapped[str] = mapped_column(
        String(12), default="good_only"
    )  # good_only|allow_bad  # noqa: E501
    default_time_grain: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )  # hour|day|week|month  # noqa: E501
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    dependencies: Mapped[list[FacilityVariableDependency]] = relationship(
        back_populates="variable",
        cascade="all, delete-orphan",
        foreign_keys="FacilityVariableDependency.variable_id",
        lazy="selectin",
    )


class FacilityVariableDependency(Base):
    __tablename__ = "facility_variable_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variable_id: Mapped[int] = mapped_column(
        ForeignKey("facility_variables.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_type: Mapped[str] = mapped_column(String(8), nullable=False)  # tag|variable
    depends_on_tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=True
    )
    depends_on_variable_id: Mapped[int | None] = mapped_column(
        ForeignKey("facility_variables.id", ondelete="CASCADE"), nullable=True
    )

    variable: Mapped[FacilityVariable] = relationship(
        back_populates="dependencies", foreign_keys=[variable_id]
    )
