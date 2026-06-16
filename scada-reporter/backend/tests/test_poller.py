"""Poller: ayarlar, grup okuma, bulk yazma, tek-tick koşusu."""

from app.core.config import settings


def test_settings_worker_pool_covers_fleet():
    assert settings.S7_MAX_WORKERS >= 27  # 27 PLC filosu
    assert settings.S7_PLC_READ_TIMEOUT > 0
