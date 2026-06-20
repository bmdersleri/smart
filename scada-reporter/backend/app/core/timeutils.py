"""Timezone helpers for serialization.

TagReading timestamps are stored as naive UTC (SQLite drops tzinfo). When we
emit them to the API we attach an explicit UTC offset so clients receive an
unambiguous instant (``...+00:00``) instead of an offset-less string that the
frontend has to patch with a manual ``+ 'Z'``.
"""

from datetime import UTC, datetime


def as_utc(dt: datetime | None) -> datetime | None:
    """Return ``dt`` as a UTC-aware datetime (read-side normalization).

    Naive values are assumed to be UTC (how they are stored); aware values are
    converted to UTC. ``None`` passes through unchanged.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def utc_iso(dt: datetime | None) -> str | None:
    """ISO-8601 string with explicit UTC offset, or ``None``."""
    norm = as_utc(dt)
    return norm.isoformat() if norm else None
