from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tag_ids: Mapped[str] = mapped_column(Text)  # JSON "[1,2,3]"
    time_range_type: Mapped[str] = mapped_column(String(20), default="last_24h")
    # last_1h|last_24h|last_7d|last_30d|custom
    custom_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    custom_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interval: Mapped[str] = mapped_column(String(20), default="hourly")
    # hourly|daily|weekly
    output_format: Mapped[str] = mapped_column(String(10), default="excel")
    # excel|pdf|json
    include_std_dev: Mapped[bool] = mapped_column(Boolean, default=True)
    include_percentiles: Mapped[bool] = mapped_column(Boolean, default=True)
    percentile_levels: Mapped[str] = mapped_column(Text, default="[10,25,50,75,90,95]")
    include_trend_line: Mapped[bool] = mapped_column(Boolean, default=True)
    anomaly_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anomaly_zscore_threshold: Mapped[float] = mapped_column(Float, default=3.0)
    show_summary_stats: Mapped[bool] = mapped_column(Boolean, default=True)
    show_trend_charts: Mapped[bool] = mapped_column(Boolean, default=True)
    show_anomaly_table: Mapped[bool] = mapped_column(Boolean, default=True)
    show_raw_data: Mapped[bool] = mapped_column(Boolean, default=False)
    grafana_panels: Mapped[str] = mapped_column(Text, default="[]")
    # JSON: [{"dashboard_uid": "scada-watchlist", "panel_id": 1, "title": "Debi"}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
