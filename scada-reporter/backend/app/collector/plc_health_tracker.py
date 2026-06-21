from __future__ import annotations

import threading

from app.monitor.detector import PlcObservation

Key = tuple[str, int, int]


class PlcHealthTracker:
    """Poller'dan beslenen, monitor'ün okuduğu in-memory PLC sağlık sayaçları."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[Key, dict] = {}

    def _blank(self, name: str, now: float) -> dict:
        return {
            "name": name,
            "good": 0,
            "bad": 0,
            "connected": False,
            "last_success_mono": None,
            "first_mono": now,
            "reconnect_times": [],
            "last_error": None,
        }

    def record_read(
        self, key: Key, name: str, good: int, bad: int, now: float, error: str | None = None
    ) -> None:
        with self._lock:
            d = self._data.setdefault(key, self._blank(name, now))
            if name:
                d["name"] = name
            d["good"] += good
            d["bad"] += bad
            if good > 0:
                d["last_success_mono"] = now
                d["last_error"] = None  # başarılı okuma hatayı temizler
            if error is not None:
                d["last_error"] = error

    def observe_connection(self, key: Key, name: str, connected: bool, now: float) -> None:
        with self._lock:
            d = self._data.setdefault(key, self._blank(name, now))
            if name:
                d["name"] = name
            if connected and not d["connected"]:
                d["reconnect_times"].append(now)
            d["connected"] = connected

    def known_keys(self) -> list[Key]:
        with self._lock:
            return list(self._data.keys())

    def snapshot(self, now: float, flap_window: float) -> list[PlcObservation]:
        with self._lock:
            out: list[PlcObservation] = []
            for key, d in self._data.items():
                d["reconnect_times"] = [t for t in d["reconnect_times"] if now - t <= flap_window]
                last = d["last_success_mono"]
                sss = (now - last) if last is not None else (now - d["first_mono"])
                out.append(
                    PlcObservation(
                        key=key,
                        name=d["name"],
                        connected=d["connected"],
                        good_count=d["good"],
                        bad_count=d["bad"],
                        seconds_since_success=sss,
                        reconnects_in_window=len(d["reconnect_times"]),
                        last_error=d["last_error"],
                    )
                )
                d["good"] = 0
                d["bad"] = 0
            return out


health_tracker = PlcHealthTracker()
