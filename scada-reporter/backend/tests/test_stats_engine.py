"""Unit tests for stats_engine — pure math, no DB, no I/O."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.stats_engine import TagStats, compute_tag_stats, detect_anomalies

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


def _ts(offset_seconds: int) -> datetime:
    return BASE_TIME + timedelta(seconds=offset_seconds)


def _readings(
    values: list[float | None],
    interval_s: int = 5,
    quality: int = 192,
) -> list[tuple[datetime, float | None, int]]:
    return [(_ts(i * interval_s), v, quality) for i, v in enumerate(values)]


# ---------------------------------------------------------------------------
# compute_tag_stats — basic
# ---------------------------------------------------------------------------


def test_empty_readings_returns_none_stats():
    stats = compute_tag_stats([], 1, "Pompa", "m3/h", [50], expected_interval_seconds=5)
    assert stats.count == 0
    assert stats.avg is None
    assert stats.std_dev is None
    assert stats.min is None
    assert stats.max is None
    assert stats.trend_slope is None
    assert stats.trend_r2 is None
    assert stats.trend_direction == "stable"
    assert stats.availability_pct == 0.0


def test_single_good_reading():
    readings = _readings([10.0])
    stats = compute_tag_stats(readings, 1, "P1", "bar", [50], expected_interval_seconds=5)
    assert stats.count == 1
    assert stats.good_quality_count == 1
    assert stats.avg == pytest.approx(10.0)
    assert stats.min == pytest.approx(10.0)
    assert stats.max == pytest.approx(10.0)
    assert stats.trend_slope is None  # need ≥2 good points
    assert stats.availability_pct == pytest.approx(100.0)


def test_mean_std_min_max():
    vals = [10.0, 20.0, 30.0, 40.0]
    readings = _readings(vals)
    stats = compute_tag_stats(readings, 1, "T", "°C", [25, 75], expected_interval_seconds=5)
    assert stats.avg == pytest.approx(25.0)
    assert stats.std_dev == pytest.approx(12.9099, rel=1e-3)  # ddof=1
    assert stats.min == pytest.approx(10.0)
    assert stats.max == pytest.approx(40.0)
    assert stats.count == 4
    assert stats.good_quality_count == 4


def test_percentiles():
    vals = list(range(1, 101))  # 1..100
    readings = _readings(vals)
    stats = compute_tag_stats(
        readings, 1, "X", "unit", [10, 25, 50, 75, 90], expected_interval_seconds=5
    )
    assert stats.percentiles[50] == pytest.approx(50.5, rel=1e-2)
    assert stats.percentiles[10] == pytest.approx(10.9, rel=1e-1)
    assert stats.percentiles[90] == pytest.approx(90.1, rel=1e-1)


def test_bad_quality_excluded_from_stats():
    readings = [
        (_ts(0), 100.0, 0),  # bad quality
        (_ts(5), 10.0, 192),
        (_ts(10), 20.0, 192),
    ]
    stats = compute_tag_stats(readings, 1, "P", "bar", [50], expected_interval_seconds=5)
    assert stats.count == 3
    assert stats.good_quality_count == 2
    assert stats.avg == pytest.approx(15.0)
    assert stats.availability_pct == pytest.approx(100 * 2 / 3, rel=1e-3)


def test_none_value_excluded_from_stats():
    readings = [
        (_ts(0), None, 192),
        (_ts(5), 10.0, 192),
        (_ts(10), 30.0, 192),
    ]
    stats = compute_tag_stats(readings, 1, "P", "bar", [50], expected_interval_seconds=5)
    assert stats.count == 3
    assert stats.good_quality_count == 2  # None treated as not-good
    assert stats.avg == pytest.approx(20.0)


def test_all_bad_quality():
    readings = _readings([5.0, 10.0], quality=0)
    stats = compute_tag_stats(readings, 1, "P", "bar", [50], expected_interval_seconds=5)
    assert stats.good_quality_count == 0
    assert stats.avg is None
    assert stats.availability_pct == 0.0


# ---------------------------------------------------------------------------
# Trend regression
# ---------------------------------------------------------------------------


def test_trend_rising():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]  # perfect linear rise
    readings = _readings(vals, interval_s=3600)  # 1-hour intervals → slope ~1 unit/h
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=3600)
    assert stats.trend_slope == pytest.approx(1.0, rel=1e-3)
    assert stats.trend_r2 == pytest.approx(1.0, rel=1e-3)
    assert stats.trend_direction == "rising"


def test_trend_falling():
    vals = [5.0, 4.0, 3.0, 2.0, 1.0]
    readings = _readings(vals, interval_s=3600)
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=3600)
    assert stats.trend_slope == pytest.approx(-1.0, rel=1e-3)
    assert stats.trend_direction == "falling"


def test_trend_stable_constant_series():
    vals = [7.0, 7.0, 7.0, 7.0]
    readings = _readings(vals, interval_s=3600)
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=3600)
    assert stats.trend_slope == pytest.approx(0.0, abs=1e-9)
    assert stats.trend_r2 is None  # ss_tot == 0, r2 undefined
    assert stats.trend_direction == "stable"


def test_rate_of_change():
    vals = [0.0, 1.0, 2.0, 3.0]  # 3 units over 3 hours → 1 unit/h
    readings = _readings(vals, interval_s=3600)
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=3600)
    assert stats.rate_of_change_per_hour == pytest.approx(1.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


def test_no_gaps_regular_interval():
    readings = _readings([1.0, 2.0, 3.0, 4.0], interval_s=5)
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=5)
    assert stats.gap_count == 0
    assert stats.gap_total_seconds == 0.0


def test_single_gap_detected():
    readings = [
        (_ts(0), 1.0, 192),
        (_ts(5), 2.0, 192),
        (_ts(25), 3.0, 192),  # 20s gap > 2*5=10s threshold
        (_ts(30), 4.0, 192),
    ]
    stats = compute_tag_stats(readings, 1, "T", "°C", [50], expected_interval_seconds=5)
    assert stats.gap_count == 1
    assert stats.gap_total_seconds == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------


def _make_stats(
    avg: float = 10.0,
    std_dev: float = 1.0,
    min_val: float = 8.0,
    max_val: float = 12.0,
) -> TagStats:
    return TagStats(
        tag_id=1,
        tag_name="TestTag",
        unit="bar",
        count=100,
        good_quality_count=100,
        availability_pct=100.0,
        avg=avg,
        std_dev=std_dev,
        variance=std_dev**2,
        min=min_val,
        max=max_val,
        percentiles={50: avg},
        trend_slope=None,
        trend_r2=None,
        trend_direction="stable",
        rate_of_change_per_hour=None,
        gap_count=0,
        gap_total_seconds=0.0,
    )


def test_no_anomalies_normal_data():
    readings = _readings([10.0, 10.5, 9.8, 10.2, 10.1])
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    assert anomalies == []


def test_zscore_anomaly_critical():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 10.0, 192),
        (_ts(10), 50.0, 192),  # z = (50-10)/1 = 40 >> 3.0
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    zscore_events = [a for a in anomalies if a.anomaly_type == "zscore"]
    assert len(zscore_events) == 1
    assert zscore_events[0].severity == "critical"
    assert zscore_events[0].value == pytest.approx(50.0)


def test_zscore_anomaly_warning():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 13.5, 192),  # z = 3.5, below 1.5*3.0=4.5 → warning
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    zscore_events = [a for a in anomalies if a.anomaly_type == "zscore"]
    assert len(zscore_events) == 1
    assert zscore_events[0].severity == "warning"


def test_alarm_min_breach():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 2.0, 192),  # below min_alarm=5.0
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=5.0, max_alarm=None
    )
    alarm_events = [a for a in anomalies if a.anomaly_type == "alarm_min"]
    assert len(alarm_events) == 1
    assert alarm_events[0].severity == "critical"


def test_alarm_max_breach():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 20.0, 192),  # above max_alarm=15.0
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=15.0
    )
    alarm_events = [a for a in anomalies if a.anomaly_type == "alarm_max"]
    assert len(alarm_events) == 1
    assert alarm_events[0].severity == "critical"


def test_quality_anomaly():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 10.0, 64),  # bad quality
    ]
    stats = _make_stats()
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    quality_events = [a for a in anomalies if a.anomaly_type == "quality"]
    assert len(quality_events) == 1
    assert quality_events[0].severity == "warning"
    assert "64" in quality_events[0].details


def test_jump_anomaly():
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 10.5, 192),
        (_ts(10), 10.0, 192),
        (_ts(15), 14.5, 192),  # jump = 4.5 > 3*1.0=3.0 → warning
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=10.0, min_alarm=None, max_alarm=None
    )
    jump_events = [a for a in anomalies if a.anomaly_type == "jump"]
    assert len(jump_events) >= 1
    assert all(e.severity == "warning" for e in jump_events)


def test_anomaly_deduplication_preserves_both_types():
    """A point that is both zscore and alarm_max should produce events for BOTH types."""
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), 50.0, 192),  # zscore AND above max_alarm=15
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=15.0
    )
    types = {a.anomaly_type for a in anomalies}
    assert "zscore" in types
    assert "alarm_max" in types


def test_anomaly_none_value_quality_event_only():
    """None value → quality event (can't compute zscore/jump), no crash."""
    readings = [
        (_ts(0), 10.0, 192),
        (_ts(5), None, 192),
    ]
    stats = _make_stats()
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    types = [a.anomaly_type for a in anomalies]
    assert "quality" in types
    assert "zscore" not in types


def test_anomalies_sorted_by_timestamp():
    readings = [
        (_ts(10), 50.0, 192),
        (_ts(0), 50.0, 192),
        (_ts(5), 50.0, 192),
    ]
    stats = _make_stats(avg=10.0, std_dev=1.0)
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    timestamps = [a.timestamp for a in anomalies]
    assert timestamps == sorted(timestamps)


def test_no_anomaly_when_std_dev_none():
    """No std_dev (e.g. single point) → zscore/jump checks skipped, no crash."""
    readings = [(_ts(0), 10.0, 192)]
    stats = _make_stats()
    stats.std_dev = None
    anomalies = detect_anomalies(
        readings, stats, zscore_threshold=3.0, min_alarm=None, max_alarm=None
    )
    # alarm checks still work; just no zscore/jump events
    zscore_events = [a for a in anomalies if a.anomaly_type in ("zscore", "jump")]
    assert zscore_events == []
