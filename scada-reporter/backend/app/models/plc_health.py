from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlcHealth(Base):
    __tablename__ = "plc_health"
    __table_args__ = (UniqueConstraint("plc_ip", "rack", "slot", name="uq_plc_health_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plc_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    plc_name: Mapped[str] = mapped_column(String(255), default="")
    rack: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int] = mapped_column(Integer, default=1)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_fail: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    good_last_cycle: Mapped[int] = mapped_column(Integer, default=0)
    bad_last_cycle: Mapped[int] = mapped_column(Integer, default=0)
    reconnects_last_min: Mapped[int] = mapped_column(Integer, default=0)
    open_incident_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
