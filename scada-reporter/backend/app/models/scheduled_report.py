from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("report_templates.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    schedule_type: Mapped[str] = mapped_column(String(20))  # cron|interval
    cron_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_minute: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    cron_day_of_week: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cron_day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apscheduler_job_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # completed|failed|running
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
