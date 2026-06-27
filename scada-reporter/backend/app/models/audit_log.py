"""Audit log model — records admin user-management actions."""

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """Immutable record of an admin action that mutates a user object."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    # Actor (the admin who performed the action). Nullable so rows survive
    # even if the actor account is later deleted.
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str] = mapped_column(String(100), nullable=False)
    # Action verb, e.g. user.create / user.update / user.role_change /
    #   user.password_reset / user.delete
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # What kind of object was changed
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # String-serialised target PK so it survives generic use (user id as str)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # JSON-encoded dict describing what changed. Stored as Text to avoid
    # dialect-specific JSON column behaviour in SQLite.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # IP address of the request, if available.
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ------------------------------------------------------------------ #
    # Convenience property: parse detail back to dict on read.
    # ------------------------------------------------------------------ #
    @property
    def detail_dict(self) -> dict:
        if self.detail is None:
            return {}
        try:
            return json.loads(self.detail)
        except ValueError, TypeError:
            return {}
