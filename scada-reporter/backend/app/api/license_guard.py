"""FastAPI-layer license enforcement: feature gating, tag quota, demo read-only.

Thin adapters over the mode-aware helpers in :mod:`app.core.license`, raising
HTTP 403 when the current license mode forbids an operation.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.license import active_tag_quota, feature_allowed, is_writable
from app.models.tag import Tag


def require_feature(feature: str) -> Callable[[], Awaitable[None]]:
    """Return a dependency that 403s when ``feature`` is not allowed in this mode."""

    async def _guard() -> None:
        if not feature_allowed(feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"License does not include the '{feature}' feature.",
            )

    return _guard


async def require_writable() -> None:
    """403 in DEMO mode — mutating operations need a license."""
    if not is_writable():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo mode is read-only. Upload a license to enable changes.",
        )


async def assert_tag_quota(db: AsyncSession = Depends(get_db), adding: int = 1) -> None:
    """403 when adding ``adding`` tags would exceed the active tag quota."""
    quota = active_tag_quota()
    if quota is None:
        return
    current = await db.scalar(select(func.count()).select_from(Tag)) or 0
    if current + adding > quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tag limit reached: limit={quota}, current={current}, requested=+{adding}.",
        )
