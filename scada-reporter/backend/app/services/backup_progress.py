"""In-process progress registry for long-running backup/restore jobs.

Backup of a multi-GB SQLite DB takes minutes (VACUUM INTO + integrity check +
zstd compress + sha256). The HTTP request that kicks it off returns immediately
and the work runs as a background task; clients then subscribe to an SSE
endpoint that polls this registry for `{phase, percent, status}`.

Single-process only (the collector/scheduler share this process). State is
ephemeral — it is not persisted and is fine to lose on restart; the durable
record lives in the `backups` table.
"""

from __future__ import annotations

from typing import TypedDict


class Progress(TypedDict):
    phase: str
    percent: float  # 0..100
    status: str  # running | done | failed
    error: str | None


_jobs: dict[str, Progress] = {}


def start(key: str) -> None:
    _jobs[key] = {"phase": "queued", "percent": 0.0, "status": "running", "error": None}


def update(key: str, *, phase: str, fraction: float) -> None:
    """Report progress for `key`. `fraction` is 0..1 within the overall job."""
    job = _jobs.get(key)
    if job is None:
        return
    job["phase"] = phase
    job["percent"] = max(0.0, min(100.0, round(fraction * 100, 1)))


def finish(key: str, *, error: str | None = None) -> None:
    job = _jobs.get(key)
    if job is None:
        job = {"phase": "done", "percent": 100.0, "status": "running", "error": None}
        _jobs[key] = job
    if error is None:
        job["status"] = "done"
        job["phase"] = "done"
        job["percent"] = 100.0
    else:
        job["status"] = "failed"
        job["error"] = error[:512]


def get(key: str) -> Progress | None:
    return _jobs.get(key)


def clear(key: str) -> None:
    _jobs.pop(key, None)
