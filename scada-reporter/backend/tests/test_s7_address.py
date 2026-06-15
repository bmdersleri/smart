"""S7 adres parser, interval parse ve PLCManager testleri."""

import pytest

from app.collector.s7_collector import PLCManager, ReadSpec, parse_address
from app.import_catalog import parse_interval


@pytest.mark.parametrize(
    ("address", "data_type", "expected"),
    [
        # DD + float32 -> 4 byte REAL
        (
            "DB301,DD7890",
            "Floating-point number 32-bit IEEE 754",
            ReadSpec("DB", 301, 7890, 0, 4, "REAL"),
        ),
        # DD + float64 -> PLC tarafında yine 4 byte REAL
        (
            "DB300,DD514",
            "Floating-point number 64-bit IEEE 754",
            ReadSpec("DB", 300, 514, 0, 4, "REAL"),
        ),
        # DBW + uint16 -> 2 byte WORD
        ("DB310,DBW90", "Unsigned 16-bit value", ReadSpec("DB", 310, 90, 0, 2, "WORD")),
        # Q çıkış biti -> PA alanı, BOOL
        ("Q254.1", "Binary Tag", ReadSpec("PA", 0, 254, 1, 1, "BOOL")),
        # legacy formatlar (geri uyum)
        ("DB1,REAL0", None, ReadSpec("DB", 1, 0, 0, 4, "REAL")),
        ("DB5,BOOL10.3", None, ReadSpec("DB", 5, 10, 3, 1, "BOOL")),
        # küçük harf + boşluk normalize edilir
        (" db2,dbw4 ", "uint16", ReadSpec("DB", 2, 4, 0, 2, "WORD")),
    ],
)
def test_parse_address(address, data_type, expected):
    assert parse_address(address, data_type) == expected


def test_parse_address_unknown_raises():
    with pytest.raises(ValueError, match="Cozumlenemeyen"):
        parse_address("GARBAGE", None)
    with pytest.raises(ValueError, match="Bilinmeyen DB operandı"):
        parse_address("DB1,XYZ4", None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5 second", 5),
        ("1 minute", 60),
        ("2 hour", 7200),
        ("10 saniye", 10),
        ("3 dakika", 180),
        (None, 5),
        ("garbage", 5),
    ],
)
def test_parse_interval(value, expected):
    assert parse_interval(value) == expected


def test_plc_manager_get_is_singleton_per_key():
    mgr = PLCManager()
    a = mgr.get("10.0.0.1", 0, 1)
    b = mgr.get("10.0.0.1", 0, 1)
    c = mgr.get("10.0.0.1", 0, 2)
    assert a is b
    assert a is not c
    assert mgr.status() == {"10.0.0.1": False}
