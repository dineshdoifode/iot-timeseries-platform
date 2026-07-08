"""
MQTT ingestion worker.

Subscribes to `phy/+/telemetry` and `phy/+/status`, persists raw messages
to `mqtt_messages` for audit/replay, parses payloads into `telemetry` /
`device_status`, and auto-registers unknown devices.

Run standalone:
    python -m app.workers.mqtt_worker
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aiomqtt
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.session import AsyncSessionLocal
from app.models.models import DeviceStatus, MqttMessage, Telemetry
from app.monitoring.metrics import (
    MQTT_CONNECTED,
    MQTT_MESSAGES_TOTAL,
    MQTT_PROCESSING_ERRORS_TOTAL,
    MQTT_RECONNECTS_TOTAL,
)
from app.repositories.device_repository import DeviceRepository

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("mqtt-worker")


def extract_device_id(topic: str) -> str | None:
    """phy/{device_id}/telemetry -> device_id"""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 3 else None


def topic_type(topic: str) -> str:
    if topic.endswith("/telemetry"):
        return "telemetry"
    if topic.endswith("/status"):
        return "status"
    return "unknown"


async def store_raw_message(
    session: AsyncSession, topic: str, device_id: str | None, qos: int,
    retained: bool, payload_raw: str, processed: bool, error: str | None = None,
) -> None:
    session.add(
        MqttMessage(
            time=datetime.now(timezone.utc),
            topic=topic,
            device_id=device_id,
            qos=qos,
            retained=retained,
            payload_raw=payload_raw,
            processed=processed,
            error=error,
        )
    )
    await session.commit()


async def handle_telemetry(session: AsyncSession, device_id: str, data: dict) -> None:
    """
    Expected payload shape (flexible/custom JSON supported via `payload`):
    {
      "metrics": {"temperature": 23.4, "humidity": 55.1},
      "unit": {"temperature": "C", "humidity": "%"},   # optional
      "quality": 1                                      # optional
    }
    Falls back to treating the whole body as one metric if "metrics" absent.
    """
    metrics: dict = data.get("metrics", {})
    units: dict = data.get("unit", {})
    quality = int(data.get("quality", 1))

    if not metrics:
        # allow flat payloads like {"temperature": 23.4}
        metrics = {k: v for k, v in data.items() if isinstance(v, (int, float))}

    for metric, value in metrics.items():
        session.add(
            Telemetry(
                time=datetime.now(timezone.utc),
                device_id=device_id,
                metric=metric,
                value=float(value),
                unit=units.get(metric),
                payload=data,
                quality=quality,
            )
        )
    await session.commit()


async def handle_status(session: AsyncSession, device_id: str, data: dict) -> None:
    status = data.get("status", "unknown")
    reason = data.get("reason")
    session.add(
        DeviceStatus(
            time=datetime.now(timezone.utc),
            device_id=device_id,
            status=status,
            reason=reason,
            metadata_=data,
        )
    )
    await session.commit()


async def process_message(message: aiomqtt.Message) -> None:
    topic = str(message.topic)
    t_type = topic_type(topic)
    device_id = extract_device_id(topic)
    payload_raw = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)

    MQTT_MESSAGES_TOTAL.labels(topic_type=t_type).inc()

    async with AsyncSessionLocal() as session:
        try:
            data = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            logger.warning("Bad JSON on %s: %s", topic, exc)
            await store_raw_message(
                session, topic, device_id, message.qos, message.retain,
                payload_raw, processed=False, error=f"json_decode_error: {exc}",
            )
            MQTT_PROCESSING_ERRORS_TOTAL.labels(topic_type=t_type).inc()
            return

        if not device_id:
            logger.warning("Could not extract device_id from topic %s", topic)
            await store_raw_message(
                session, topic, device_id, message.qos, message.retain,
                payload_raw, processed=False, error="missing_device_id",
            )
            MQTT_PROCESSING_ERRORS_TOTAL.labels(topic_type=t_type).inc()
            return

        try:
            device_repo = DeviceRepository(session)
            await device_repo.upsert_from_telemetry(device_id)

            if t_type == "telemetry":
                await handle_telemetry(session, device_id, data)
            elif t_type == "status":
                await handle_status(session, device_id, data)

            await store_raw_message(
                session, topic, device_id, message.qos, message.retain,
                payload_raw, processed=True,
            )
        except Exception as exc:  # noqa: BLE001 — route any failure to the DLQ row instead of crashing the worker
            logger.exception("Failed to process message on %s", topic)
            await session.rollback()
            await store_raw_message(
                session, topic, device_id, message.qos, message.retain,
                payload_raw, processed=False, error=str(exc),
            )
            MQTT_PROCESSING_ERRORS_TOTAL.labels(topic_type=t_type).inc()


async def run_worker() -> None:
    min_delay = settings.mqtt_reconnect_min_delay
    max_delay = settings.mqtt_reconnect_max_delay
    delay = min_delay

    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker_host,
                port=settings.mqtt_broker_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
                identifier=settings.mqtt_client_id,
                keepalive=settings.mqtt_keepalive,
            ) as client:
                MQTT_CONNECTED.set(1)
                delay = min_delay
                logger.info(
                    "Connected to MQTT broker %s:%s",
                    settings.mqtt_broker_host,
                    settings.mqtt_broker_port,
                )
                await client.subscribe(settings.mqtt_telemetry_topic, qos=1)
                await client.subscribe(settings.mqtt_status_topic, qos=1)

                async for message in client.messages:
                    await process_message(message)

        except aiomqtt.MqttError as exc:
            MQTT_CONNECTED.set(0)
            MQTT_RECONNECTS_TOTAL.inc()
            logger.warning(
                "MQTT connection lost (%s). Reconnecting in %ss...", exc, delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


def main() -> None:
    start_http_server(9100)
    logger.info("MQTT worker metrics exposed on :9100/metrics")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("MQTT worker stopped by user")


if __name__ == "__main__":
    main()
