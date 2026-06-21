from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"warning": 0, "critical": 1}


@dataclass(frozen=True)
class AlertPayload:
    plc_ip: str
    plc_name: str
    kind: str
    severity: str
    message: str
    event: str  # "opened" | "resolved"
    detail: dict


def _passes_severity(severity: str) -> bool:
    floor = _SEVERITY_RANK.get(settings.ALERT_MIN_SEVERITY, 0)
    return _SEVERITY_RANK.get(severity, 0) >= floor


async def _send_webhook(payload: AlertPayload) -> None:
    body = {
        "plc_ip": payload.plc_ip,
        "plc_name": payload.plc_name,
        "kind": payload.kind,
        "severity": payload.severity,
        "message": payload.message,
        "event": payload.event,
        "detail": payload.detail,
    }
    async with httpx.AsyncClient(timeout=10.0) as cx:
        await cx.post(settings.ALERT_WEBHOOK_URL, json=body)


async def _send_email(payload: AlertPayload) -> None:
    recipients = [r.strip() for r in settings.ALERT_EMAIL_TO.split(",") if r.strip()]
    if not recipients:
        return
    msg = EmailMessage()
    msg["Subject"] = (
        f"[SCADA {payload.severity.upper()}] {payload.plc_name} {payload.kind} ({payload.event})"
    )
    msg["From"] = settings.ALERT_EMAIL_FROM or settings.SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"PLC: {payload.plc_name} ({payload.plc_ip})\n"
        f"Sorun: {payload.kind} / {payload.severity}\n"
        f"Durum: {payload.event}\n"
        f"Mesaj: {payload.message}\n"
        f"Detay: {payload.detail}\n"
    )

    def _send_sync() -> None:
        import smtplib

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)

    await asyncio.get_running_loop().run_in_executor(None, _send_sync)


async def dispatch(payload: AlertPayload) -> None:
    """Etkin kanallara uyarı gönder. Severity kapısı + kanal hatalarını yut."""
    if not _passes_severity(payload.severity):
        return
    if settings.ALERT_WEBHOOK_URL:
        try:
            await _send_webhook(payload)
        except Exception as e:
            logger.warning("Webhook uyarı gönderilemedi: %s", e)
    if settings.ALERT_EMAIL_ENABLED:
        try:
            await _send_email(payload)
        except Exception as e:
            logger.warning("E-posta uyarı gönderilemedi: %s", e)
