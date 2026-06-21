"""Audit logging helper.

Call ``record_audit`` inside an endpoint's database transaction, *before*
``await db.commit()``.  The helper adds the row to the session but intentionally
does NOT commit — the calling endpoint owns the transaction boundary.
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User


async def record_audit(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: int | str | None = None,
    detail: dict | None = None,
    ip: str | None = None,
) -> None:
    """Add an AuditLog row to *db* within the current transaction.

    Parameters
    ----------
    db:
        Active async session — the row is added but **not** committed here.
    actor:
        The admin user performing the action. May be ``None`` if the actor
        can no longer be determined (e.g. system action).
    action:
        Dot-separated verb, e.g. ``"user.create"``.
    target_type:
        Object type being acted on, e.g. ``"user"``.
    target_id:
        Primary key of the target object (converted to ``str``).
    detail:
        Small dict describing what changed. Passwords must **never** appear here.
    ip:
        IP address of the HTTP request, or ``None``.
    """
    log = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        actor_username=actor.username if actor is not None else "system",
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=json.dumps(detail) if detail is not None else None,
        ip=ip,
    )
    db.add(log)
