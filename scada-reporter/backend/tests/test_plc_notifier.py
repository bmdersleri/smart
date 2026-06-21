import pytest

from app.monitor import notifier
from app.monitor.notifier import AlertPayload


def _payload(severity="critical", event="opened"):
    return AlertPayload(
        plc_ip="10.0.0.1",
        plc_name="PLC1",
        kind="disconnected",
        severity=severity,
        message="down",
        event=event,
        detail={},
    )


@pytest.mark.asyncio
async def test_dispatch_calls_enabled_channels(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")
    monkeypatch.setattr(notifier.settings, "ALERT_EMAIL_ENABLED", True)
    monkeypatch.setattr(notifier.settings, "ALERT_MIN_SEVERITY", "warning")
    monkeypatch.setattr(notifier, "_send_webhook", lambda p: calls.append("webhook") or _noop())
    monkeypatch.setattr(notifier, "_send_email", lambda p: calls.append("email") or _noop())
    await notifier.dispatch(_payload())
    assert set(calls) == {"webhook", "email"}


@pytest.mark.asyncio
async def test_severity_gate_blocks_low_severity(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")
    monkeypatch.setattr(notifier.settings, "ALERT_MIN_SEVERITY", "critical")
    monkeypatch.setattr(notifier, "_send_webhook", lambda p: calls.append("webhook") or _noop())
    await notifier.dispatch(_payload(severity="warning"))
    assert calls == []  # warning < critical -> blocked


@pytest.mark.asyncio
async def test_channel_error_is_swallowed(monkeypatch):
    monkeypatch.setattr(notifier.settings, "ALERT_WEBHOOK_URL", "http://hook")

    async def _boom(p):
        raise RuntimeError("network down")

    monkeypatch.setattr(notifier, "_send_webhook", _boom)
    # must not raise
    await notifier.dispatch(_payload())


async def _noop():
    return None
