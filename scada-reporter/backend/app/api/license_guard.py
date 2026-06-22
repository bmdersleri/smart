"""FastAPI-layer license enforcement: feature gating + tag quota.

Thin adapters over the pure helpers in :mod:`app.core.license`, translating a
:class:`~app.core.license.LicenseLimitError` into an HTTP 403 response.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.license import (
    LicenseLimitError,
    enforce_feature,
    enforce_tag_quota,
    get_active_license,
)
from app.models.tag import Tag


def require_feature(feature: str) -> Callable[[], Awaitable[None]]:
    """Return a dependency that 403s when ``feature`` is not licensed."""

    async def _guard() -> None:
        try:
            enforce_feature(get_active_license(), feature)
        except LicenseLimitError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _guard


async def assert_tag_quota(db: AsyncSession = Depends(get_db), adding: int = 1) -> None:
    """403 when adding ``adding`` tags would exceed the licensed ``max_tags``."""
    info = get_active_license()
    if info is None or info.max_tags is None:
        return
    current = await db.scalar(select(func.count()).select_from(Tag)) or 0
    try:
        enforce_tag_quota(info, current, adding)
    except LicenseLimitError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
