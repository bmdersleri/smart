from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY = {
    "disconnected": "critical",
    "stale_data": "critical",
    "partial_bad": "warning",
    "flapping": "warning",
}


@dataclass(frozen=True)
class PlcObservation:
    key: tuple[str, int, int]
    name: str
    connected: bool
    good_count: int
    bad_count: int
    seconds_since_success: float
    reconnects_in_window: int
    last_error: str | None = None


@dataclass(frozen=True)
class DetectorConfig:
    stale_seconds: float
    partial_bad_ratio: float
    partial_bad_cycles: int
    flap_count: int
    recover_cycles: int


@dataclass
class OpenIncident:
    kind: str
    severity: str
    opened_at_mono: float
    clean_cycles: int = 0
    detail: dict = field(default_factory=dict)


@dataclass
class PlcMonitorState:
    open: dict[str, OpenIncident] = field(default_factory=dict)
    partial_bad_streak: int = 0
    disconnected_streak: int = 0


@dataclass
class EvalResult:
    state: PlcMonitorState
    opened: list[OpenIncident]
    resolved: list[str]


def _detail(kind: str, obs: PlcObservation, cfg: DetectorConfig) -> dict:
    return {
        "kind": kind,
        "good": obs.good_count,
        "bad": obs.bad_count,
        "seconds_since_success": round(obs.seconds_since_success, 1),
        "reconnects_in_window": obs.reconnects_in_window,
    }


def evaluate(
    prev: PlcMonitorState, obs: PlcObservation, cfg: DetectorConfig, now: float
) -> EvalResult:
    state = PlcMonitorState(
        open={k: OpenIncident(**vars(v)) for k, v in prev.open.items()},
        partial_bad_streak=prev.partial_bad_streak,
        disconnected_streak=prev.disconnected_streak,
    )
    opened: list[OpenIncident] = []
    resolved: list[str] = []

    # streak güncellemeleri
    state.disconnected_streak = state.disconnected_streak + 1 if not obs.connected else 0

    total = obs.good_count + obs.bad_count
    bad_ratio = (obs.bad_count / total) if total else 0.0
    if obs.connected and total > 0 and bad_ratio > cfg.partial_bad_ratio:
        state.partial_bad_streak += 1
    else:
        state.partial_bad_streak = 0

    conditions = {
        "disconnected": state.disconnected_streak >= 2,
        "stale_data": obs.connected and obs.seconds_since_success >= cfg.stale_seconds,
        "partial_bad": state.partial_bad_streak >= cfg.partial_bad_cycles,
        "flapping": obs.reconnects_in_window >= cfg.flap_count,
    }

    for kind, active in conditions.items():
        existing = state.open.get(kind)
        if active:
            if existing is None:
                inc = OpenIncident(
                    kind=kind,
                    severity=SEVERITY[kind],
                    opened_at_mono=now,
                    clean_cycles=0,
                    detail=_detail(kind, obs, cfg),
                )
                state.open[kind] = inc
                opened.append(inc)
            else:
                existing.clean_cycles = 0
                existing.detail = _detail(kind, obs, cfg)
        elif existing is not None:
            existing.clean_cycles += 1
            if existing.clean_cycles >= cfg.recover_cycles:
                del state.open[kind]
                resolved.append(kind)

    return EvalResult(state=state, opened=opened, resolved=resolved)
