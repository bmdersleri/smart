from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExcelTemplate(Base):
    __tablename__ = "excel_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    file_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    date_col: Mapped[str] = mapped_column(String(4), nullable=False)
    data_start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    date_mode: Mapped[str] = mapped_column(String(8), default="write")  # write|match
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    columns: Mapped[list["ExcelTemplateColumn"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ExcelTemplateColumn.id",
        lazy="selectin",
    )


class ExcelTemplateColumn(Base):
    __tablename__ = "excel_template_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("excel_templates.id", ondelete="CASCADE"), nullable=False
    )
    col_letter: Mapped[str] = mapped_column(String(4), nullable=False)
    tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )
    agg: Mapped[str] = mapped_column(String(8), default="avg")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    template: Mapped["ExcelTemplate"] = relationship(back_populates="columns")
