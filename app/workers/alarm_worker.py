"""
Periodic alarm evaluation worker.

Runs in its own container (see docker-compose `alarm-worker` service),
polling enabled alarm_rules on a fixed interval and evaluating each rule
against the latest telemetry/status for its target devices. Firing an
alarm inserts a row into `alarms` (idempotent per device+rule — see
AlarmRepository.get_active_for_rule) and fans out notifications; the
condition clearing auto-resolves the open alarm.

Run standalone:
    python -m app.workers.alarm_worker
"""

import asyncio
import logging
from datetime import datetime, timezone

import aiomqtt
from prometheus_client import Counter, start_http_server

from app.config.settings import get_settings
from app.database.session import AsyncSessionLocal
from app.models.models import Alarm, AlarmRule
from app.repositories.alarm_repository import AlarmRepository, AlarmRuleRepository
from app.services import alarm_engine
from app.services.notifications import notify_email, notify_mqtt, notify_slack, notify_webhook

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("alarm-worker")

ALARMS_FIRED_TOTAL = Counter("alarms_fired_total", "Total alarms fired", ["rule_type", "severity"])
ALARMS_RESOLVED_TOTAL = Counter("alarms_resolved_total", "Total alarms auto-resolved", ["rule_type"])


async def dispatch_notifications(rule: AlarmRule, device_id: str, message: str, mqtt_client) -> None:
    payload = {
        "device_id": device_id,
        "rule_name": rule.name,
        "severity": rule.severity,
        "message": message,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    channels = rule.notify_channels or []

    if "mqtt" in channels and mqtt_client is not None:
        await notify_mqtt(mqtt_client, device_id, payload)
    if "webhook" in channels and settings.alarm_webhook_url:
        await notify_webhook(settings.alarm_webhook_url, payload)
    if "slack" in channels and settings.alarm_slack_webhook_url:
        await notify_slack(settings.alarm_slack_webhook_url, f"[{rule.severity.upper()}] {device_id}: {message}")
    if "email" in channels and settings.alarm_smtp_host and settings.alarm_email_to:
        to_addrs = [addr.strip() for addr in settings.alarm_email_to.split(",") if addr.strip()]
        notify_email(
            settings.alarm_smtp_host,
            settings.alarm_smtp_port,
            settings.alarm_email_from or "alerts@iot-platform.local",
            to_addrs,
            subject=f"[{rule.severity.upper()}] Alarm: {rule.name} ({device_id})",
            body=message,
        )


async def _evaluate_for_device(rule: AlarmRule, device_id: str, alarm_repo: AlarmRepository) -> alarm_engine.EvaluationResult:
    if rule.rule_type == "threshold_gt":
        reading = await alarm_repo.latest_telemetry_value(device_id, rule.metric)
        return alarm_engine.evaluate_threshold_gt(rule, reading.value if reading else None)

    if rule.rule_type == "threshold_lt":
        reading = await alarm_repo.latest_telemetry_value(device_id, rule.metric)
        return alarm_engine.evaluate_threshold_lt(rule, reading.value if reading else None)

    if rule.rule_type == "battery_low":
        reading = await alarm_repo.latest_telemetry_value(device_id, rule.metric or "battery")
        return alarm_engine.evaluate_battery_low(rule, reading.value if reading else None)

    if rule.rule_type == "device_offline":
        status_row = await alarm_repo.latest_status(device_id)
        return alarm_engine.evaluate_device_offline(
            rule,
            status_row.status if status_row else None,
            status_row.time if status_row else None,
        )

    if rule.rule_type == "sensor_timeout":
        reading = await alarm_repo.latest_telemetry_value(device_id, rule.metric)
        return alarm_engine.evaluate_sensor_timeout(rule, reading.time if reading else None)

    logger.warning("Unknown rule_type '%s' on rule '%s' — skipping", rule.rule_type, rule.name)
    return alarm_engine.EvaluationResult(triggered=False)


async def evaluate_rule(rule: AlarmRule, mqtt_client) -> None:
    async with AsyncSessionLocal() as session:
        rule_repo = AlarmRuleRepository(session)
        alarm_repo = AlarmRepository(session)

        device_ids = await rule_repo.target_devices(rule)
        for device_id in device_ids:
            result = await _evaluate_for_device(rule, device_id, alarm_repo)

            if result.triggered:
                existing = await alarm_repo.get_active_for_rule(device_id, rule.id)
                if existing is None:
                    alarm = Alarm(
                        device_id=device_id,
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=result.message,
                        triggered_at=datetime.now(timezone.utc),
                        is_active=True,
                    )
                    await alarm_repo.create(alarm)
                    ALARMS_FIRED_TOTAL.labels(rule_type=rule.rule_type, severity=rule.severity).inc()
                    logger.warning("ALARM FIRED: %s on %s - %s", rule.name, device_id, result.message)
                    await dispatch_notifications(rule, device_id, result.message, mqtt_client)
            else:
                existing = await alarm_repo.get_active_for_rule(device_id, rule.id)
                if existing is not None:
                    ALARMS_RESOLVED_TOTAL.labels(rule_type=rule.rule_type).inc()
                await alarm_repo.auto_resolve_for_rule(device_id, rule.id)


async def evaluation_cycle(mqtt_client) -> None:
    async with AsyncSessionLocal() as session:
        rule_repo = AlarmRuleRepository(session)
        rules = await rule_repo.list(enabled_only=True)

    for rule in rules:
        try:
            await evaluate_rule(rule, mqtt_client)
        except Exception:  # noqa: BLE001 - one bad rule must not stop the others
            logger.exception("Failed evaluating rule '%s' (id=%s)", rule.name, rule.id)


async def run_worker() -> None:
    interval = settings.device_offline_check_interval_seconds

    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker_host,
                port=settings.mqtt_broker_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
                identifier="alarm-worker",
            ) as client:
                logger.info("Alarm worker connected to MQTT broker, evaluating every %ss", interval)
                while True:
                    await evaluation_cycle(client)
                    await asyncio.sleep(interval)
        except aiomqtt.MqttError as exc:
            logger.warning(
                "MQTT connection lost in alarm worker (%s); retrying in 5s. "
                "Non-MQTT alarm channels keep working via a null client meanwhile.", exc,
            )
            await evaluation_cycle(None)
            await asyncio.sleep(5)


def main() -> None:
    start_http_server(9101)
    logger.info("Alarm worker metrics exposed on :9101/metrics")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Alarm worker stopped by user")


if __name__ == "__main__":
    main()
