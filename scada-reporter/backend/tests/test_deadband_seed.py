"""Toplu deadband tier hesaplama mantığı."""

from app.seed_deadband import compute_deadband

FLOAT32 = "Floating-point number 32-bit IEEE 754"
FLOAT64 = "Floating-point number 64-bit IEEE 754"
UINT16 = "Unsigned 16-bit value"
BINARY = "Binary Tag"


def test_binary_gets_no_deadband():
    assert compute_deadband(BINARY, 1.0) is None


def test_uint16_discrete_gets_no_deadband():
    assert compute_deadband(UINT16, 5.0) is None


def test_float_tiers_by_magnitude():
    assert compute_deadband(FLOAT32, 5.0) == 0.1  # <10
    assert compute_deadband(FLOAT32, 50.0) == 0.5  # <100
    assert compute_deadband(FLOAT32, 500.0) == 2.0  # <1000
    assert compute_deadband(FLOAT32, 5000.0) == 10.0  # <100k
    assert compute_deadband(FLOAT32, 500000.0) == 50.0  # >=100k


def test_float_negative_uses_absolute():
    assert compute_deadband(FLOAT32, -500.0) == 2.0


def test_float_zero_or_none_uses_default():
    assert compute_deadband(FLOAT64, 0.0) == 0.5
    assert compute_deadband(FLOAT64, None) == 0.5


def test_garbage_huge_value_uses_default():
    # bozuk/init edilmemiş PLC okuması -> tier yerine güvenli varsayılan
    assert compute_deadband(FLOAT32, 1.0e35) == 0.5
