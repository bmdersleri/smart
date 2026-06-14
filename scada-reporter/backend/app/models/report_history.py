from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportHistory(Base):
    __tablename__ = "report_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tag_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: "[1,2,3]"
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)  # "hourly"|"daily"
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # "excel"|"json"
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
