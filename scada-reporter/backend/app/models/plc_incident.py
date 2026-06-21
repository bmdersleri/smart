from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


class PlcIncident(Base):
    __tablename__ = "plc_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plc_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    plc_name: Mapped[str] = mapped_column(String(255), default="")
    rack: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
