from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(50), default="")
    channel: Mapped[str] = mapped_column(String(255), default="")  # OPC UA channel/group
    device: Mapped[str] = mapped_column(String(255), default="")  # PLC adı

    # Çoklu-PLC + mutlak adres (WinCC export'tan)
    plc_name: Mapped[str] = mapped_column(String(255), default="")  # bağlantı adı (CAMUR_DRYER1)
    plc_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    plc_rack: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    plc_slot: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    # WinCC operand adresi, ör. DB301,DD7890 veya Q254.1
    s7_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_type: Mapped[str] = mapped_column(String(32), default="")  # float32 / uint16 / Binary
    sample_interval: Mapped[int] = mapped_column(Integer, server_default="5", default=5)  # saniye
    long_term: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    daily_tracking: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_alarm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    readings: Mapped[list["TagReading"]] = relationship(back_populates="tag")


class TagReading(Base):
    __tablename__ = "tag_readings"

    __table_args__ = (PrimaryKeyConstraint("tag_id", "timestamp"),)

    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=True)
    quality: Mapped[int] = mapped_column(Integer, default=192)  # OPC quality: 192=Good
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    tag: Mapped["Tag"] = relationship(back_populates="readings")
