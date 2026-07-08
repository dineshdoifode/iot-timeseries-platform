"""
Fan-out notification dispatch for fired/resolved alarms.
Each channel failure is logged and swallowed independently so one broken
channel (e.g. bad SMTP creds) never blocks the others or the alarm engine.
"""

import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("notifications")
settings = get_settings()


async def notify_webhook(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception:
        logger.exception("Webhook notification failed (url=%s)", url)


async def notify_slack(webhook_url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            resp.raise_for_status()
    except Exception:
        logger.exception("Slack notification failed")


def notify_email(smtp_host: str, smtp_port: int, from_addr: str, to_addrs: list[str], subject: str, body: str) -> None:
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.sendmail(from_addr, to_addrs, msg.as_string())
    except Exception:
        logger.exception("Email notification failed")


async def notify_mqtt(mqtt_client, device_id: str, payload: dict) -> None:
    """Publishes the alarm to alarms/{device_id} so downstream systems (HMI, other
    services) can react in real time without polling the REST API."""
    try:
        import json

        await mqtt_client.publish(f"alarms/{device_id}", json.dumps(payload), qos=1)
    except Exception:
        logger.exception("MQTT alarm notification failed (device_id=%s)", device_id)
