"""Trend zaman serisi downsample (max_points)."""

from app.api.dashboard import downsample


def test_downsample_returns_all_when_under_limit():
    data = [{"t": str(i), "v": float(i)} for i in range(5)]
    assert downsample(data, 100) == data


def test_downsample_none_limit_returns_all():
    data = [{"t": str(i), "v": float(i)} for i in range(50)]
    assert downsample(data, None) == data


def test_downsample_caps_point_count():
    data = [{"t": str(i), "v": float(i)} for i in range(1000)]
    out = downsample(data, 100)
    assert len(out) <= 100


def test_downsample_keeps_first_and_last():
    data = [{"t": str(i), "v": float(i)} for i in range(1000)]
    out = downsample(data, 100)
    assert out[0] == data[0]
    assert out[-1] == data[-1]
