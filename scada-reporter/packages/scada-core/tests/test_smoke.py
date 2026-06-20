# tests/test_smoke.py
import scada_core


def test_package_imports():
    assert scada_core.__version__ == "0.1.0"
