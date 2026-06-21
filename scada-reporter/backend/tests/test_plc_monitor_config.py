# tests/test_plc_monitor_config.py
from app.core.config import Settings


def test_monitor_defaults():
    s = Settings()
    assert s.PLC_MONITOR_INTERVAL == 10
    assert s.PLC_STALE_SECONDS == 60.0
    assert s.PLC_PARTIAL_BAD_RATIO == 0.5
    assert s.PLC_FLAP_COUNT == 3
    assert s.PLC_RECOVER_CYCLES == 2
    assert s.ALERT_EMAIL_ENABLED is False
    assert s.ALERT_WEBHOOK_URL == ""


def test_config_warns_when_email_enabled_but_unconfigured():
    s = Settings(ENVIRONMENT="production", ALERT_EMAIL_ENABLED=True, SMTP_HOST="")
    warnings = s.config_warnings()
    assert any("SMTP" in w for w in warnings)
