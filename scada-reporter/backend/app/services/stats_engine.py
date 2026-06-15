from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass
class TagStats:
    tag_id: int
    tag_name: str
    unit: str
    count: int
    good_quality_count: int
    availability_pct: float
    avg: float | None
    std_dev: float | None
    variance: float | None
    min: float | None
    max: float | None
    percentiles: dict[int, float]
    trend_slope: float | None  # units per hour
    trend_r2: float | None
    trend_direction: str  # rising|falling|stable
    rate_of_change_per_hour: float | None
    gap_count: int
    gap_total_seconds: float


@dataclass
class AnomalyEvent:
    timestamp: datetime
    value: float | None
    anomaly_type: str  # zscore|jump|alarm_min|alarm_max|quality
    severity: str  # warning|critical
    details: str


def compute_tag_stats(
    readings: list[tuple[datetime, float | None, int]],
    tag_id: int,
    tag_name: str,
    unit: str,
    percentile_levels: list[int],
    expected_interval_seconds: int = 5,
) -> TagStats:
    count = len(readings)

    good = [(ts, v) for ts, v, q in readings if v is not None and q == 192]
    good_quality_count = len(good)
    availability_pct = (good_quality_count / count * 100) if count > 0 else 0.0

    if not good:
        return TagStats(
            tag_id=tag_id,
            tag_name=tag_name,
            unit=unit,
            count=count,
            good_quality_count=0,
            availability_pct=availability_pct,
            avg=None,
            std_dev=None,
            variance=None,
            min=None,
            max=None,
            percentiles={},
            trend_slope=None,
            trend_r2=None,
            trend_direction="stable",
            rate_of_change_per_hour=None,
            gap_count=0,
            gap_total_seconds=0.0,
        )

    timestamps, vals_list = zip(*good, strict=False)
    vals = np.array(vals_list, dtype=float)

    avg = float(np.mean(vals))
    std_dev = float(np.std(vals, ddof=1)) if len(vals) >= 2 else None
    variance = float(np.var(vals, ddof=1)) if len(vals) >= 2 else None
    v_min = float(np.min(vals))
    v_max = float(np.max(vals))

    pct = {}
    if len(vals) >= 1:
        for level in percentile_levels:
            pct[level] = float(np.percentile(vals, level))

    # Trend regression (numpy only — no scipy)
    trend_slope: float | None = None
    trend_r2: float | None = None
    trend_direction = "stable"
    rate_of_change_per_hour: float | None = None

    if len(vals) >= 2:
        t0 = timestamps[0]
        x = np.array([(t - t0).total_seconds() / 3600.0 for t in timestamps])
        slope, intercept = np.polyfit(x, vals, 1)
        trend_slope = float(slope)

        pred = slope * x + intercept
        ss_res = float(np.sum((vals - pred) ** 2))
        ss_tot = float(np.sum((vals - vals.mean()) ** 2))
        trend_r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else None

        total_hours = x[-1]
        rate_of_change_per_hour = (
            float((vals[-1] - vals[0]) / total_hours) if total_hours > 0 else 0.0
        )

        # direction: threshold = 1% of std/hour; constant series stays stable
        if ss_tot == 0:
            trend_direction = "stable"
        else:
            threshold = 0.01 * (float(std_dev) if std_dev else 0.0)
            if trend_slope > threshold:
                trend_direction = "rising"
            elif trend_slope < -threshold:
                trend_direction = "falling"

    # Gap detection (uses all readings, not just good)
    all_ts = sorted(ts for ts, _v, _q in readings)
    gap_count = 0
    gap_total_seconds = 0.0
    gap_threshold = 2 * expected_interval_seconds
    for i in range(1, len(all_ts)):
        diff = (all_ts[i] - all_ts[i - 1]).total_seconds()
        if diff > gap_threshold:
            gap_count += 1
            gap_total_seconds += diff

    return TagStats(
        tag_id=tag_id,
        tag_name=tag_name,
        unit=unit,
        count=count,
        good_quality_count=good_quality_count,
        availability_pct=availability_pct,
        avg=avg,
        std_dev=std_dev,
        variance=variance,
        min=v_min,
        max=v_max,
        percentiles=pct,
        trend_slope=trend_slope,
        trend_r2=trend_r2,
        trend_direction=trend_direction,
        rate_of_change_per_hour=rate_of_change_per_hour,
        gap_count=gap_count,
        gap_total_seconds=gap_total_seconds,
    )


def detect_anomalies(
    readings: list[tuple[datetime, float | None, int]],
    stats: TagStats,
    zscore_threshold: float,
    min_alarm: float | None,
    max_alarm: float | None,
) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []
    avg = stats.avg
    std_dev = stats.std_dev

    sorted_readings = sorted(readings, key=lambda r: r[0])
    prev_value: float | None = None

    for ts, value, quality in sorted_readings:
        # Quality check: bad quality code OR missing value
        if quality != 192 or value is None:
            events.append(
                AnomalyEvent(
                    timestamp=ts,
                    value=value,
                    anomaly_type="quality",
                    severity="warning",
                    details=f"quality={quality}" if quality != 192 else "value=None",
                )
            )

        if value is None:
            prev_value = None
            continue

        # Z-score check
        if avg is not None and std_dev is not None and std_dev > 0:
            z = abs(value - avg) / std_dev
            if z > zscore_threshold:
                severity = "critical" if z > 1.5 * zscore_threshold else "warning"
                events.append(
                    AnomalyEvent(
                        timestamp=ts,
                        value=value,
                        anomaly_type="zscore",
                        severity=severity,
                        details=f"z={z:.2f} (mean={avg:.3f}, σ={std_dev:.3f})",
                    )
                )

        # Jump check
        if prev_value is not None and std_dev is not None and std_dev > 0:
            jump = abs(value - prev_value)
            if jump > 3 * std_dev:
                events.append(
                    AnomalyEvent(
                        timestamp=ts,
                        value=value,
                        anomaly_type="jump",
                        severity="warning",
                        details=f"jump={jump:.3f} (3σ={3 * std_dev:.3f})",
                    )
                )

        # Alarm threshold checks
        if min_alarm is not None and value < min_alarm:
            events.append(
                AnomalyEvent(
                    timestamp=ts,
                    value=value,
                    anomaly_type="alarm_min",
                    severity="critical",
                    details=f"value={value:.3f} < min_alarm={min_alarm}",
                )
            )
        if max_alarm is not None and value > max_alarm:
            events.append(
                AnomalyEvent(
                    timestamp=ts,
                    value=value,
                    anomaly_type="alarm_max",
                    severity="critical",
                    details=f"value={value:.3f} > max_alarm={max_alarm}",
                )
            )

        prev_value = value

    return sorted(events, key=lambda e: e.timestamp)
