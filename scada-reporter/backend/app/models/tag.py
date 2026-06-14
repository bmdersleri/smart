from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    PrimaryKeyConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.core.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(50), default="")
    channel: Mapped[str] = mapped_column(
        String(255), default=""
    )  # OPC UA channel/group
    device: Mapped[str] = mapped_column(String(255), default="")  # PLC adı
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
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
