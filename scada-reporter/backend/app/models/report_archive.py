from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportArchive(Base):
    __tablename__ = "report_archive"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_reports.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|running|completed|failed
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual|scheduled
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_ids: Mapped[str] = mapped_column(Text)  # JSON "[1,2,3]"
    start: Mapped[datetime] = mapped_column(DateTime)  # data period start
    end: Mapped[datetime] = mapped_column(DateTime)  # data period end
    interval: Mapped[str] = mapped_column(String(20))
    output_format: Mapped[str] = mapped_column(String(10))
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_json: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )  # gzip-compressed summary
    variable_refs_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: çözülen (variable_id, code, version, window) — denetim/sürüm damgası
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("idx_report_archive_template_id", "template_id"),
        Index("idx_report_archive_status", "status"),
    )
