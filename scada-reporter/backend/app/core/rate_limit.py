"""
Login rate limiter — dependency-free, in-process sliding window.

Design notes
------------
* State is a module-level dict; it is per-process (not shared across multiple
  Uvicorn workers).  This is intentional: the limiter provides defence-in-depth
  against trivial brute-force from a single client.  A Redis-backed global
  limiter (slowapi etc.) can be layered on top when multi-worker coordination
  is needed.
* The key is (ip, username).  An attacker trying many usernames still
  accumulates failures per-username so legitimate users on the same IP are not
  collateral damage.
* time.monotonic() is used so the tests can monkeypatch it without touching
  wall-clock time.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.core.config import settings

if TYPE_CHECKING:
    pass

# (ip, username) -> list[float]  (monotonic timestamps of failed attempts)
_failures: dict[tuple[str, str], list[float]] = {}


def _key(ip: str | None, username: str) -> tuple[str, str]:
    return (ip or "unknown", username)


def _prune(key: tuple[str, str]) -> list[float]:
    """Return failure timestamps still inside the window (mutates store in-place)."""
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    cutoff = time.monotonic() - window
    recent = [t for t in _failures.get(key, []) if t > cutoff]
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return recent


def check_and_raise(ip: str | None, username: str) -> None:
    """Raise HTTP 429 if the (ip, username) pair has exceeded the failure quota.

    Call this at the *start* of a login handler, before credential verification.
    No-op when LOGIN_RATE_LIMIT_ENABLED is False.
    """
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        return
    recent = _prune(_key(ip, username))
    if len(recent) >= settings.LOGIN_RATE_LIMIT_MAX:
        window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
        raise HTTPException(
            status_code=429,
            detail=(f"Çok fazla başarısız giriş denemesi. {window} saniye sonra tekrar deneyin."),
            headers={"Retry-After": str(window)},
        )


def record_failure(ip: str | None, username: str) -> None:
    """Record a failed login attempt for (ip, username)."""
    key = _key(ip, username)
    _prune(key)  # clean up first so old entries don't linger
    _failures.setdefault(key, []).append(time.monotonic())


def reset(ip: str | None, username: str) -> None:
    """Clear the failure counter for (ip, username) after a successful login."""
    _failures.pop(_key(ip, username), None)


def reset_all() -> None:
    """Clear ALL failure counters.  Call from test fixtures for isolation."""
    _failures.clear()
