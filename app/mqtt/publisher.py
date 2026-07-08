"""
Long-lived MQTT publish connection for the API process.

A fresh connection per REST publish call would add ~100ms+ of TCP/MQTT
handshake latency to every request. Instead we open one client at app
startup and reuse it, with a lock so concurrent publishes don't race on
the same connection, and automatic reconnect-on-failure.
"""

import asyncio
import logging

import aiomqtt

from app.config.settings import get_settings

logger = logging.getLogger("mqtt-publisher")
settings = get_settings()


class MqttPublisher:
    def __init__(self):
        self._client: aiomqtt.Client | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def start(self) -> None:
        self._client = aiomqtt.Client(
            hostname=settings.mqtt_broker_host,
            port=settings.mqtt_broker_port,
            username=settings.mqtt_username or None,
            password=settings.mqtt_password or None,
            identifier="iot-api-publisher",
        )
        await self._client.__aenter__()
        self._connected = True
        logger.info("API MQTT publisher connected")

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._connected = False
            logger.info("API MQTT publisher disconnected")

    async def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        async with self._lock:
            if not self._connected or self._client is None:
                raise RuntimeError("MQTT publisher is not connected")
            try:
                await self._client.publish(topic, payload, qos=qos, retain=retain)
            except aiomqtt.MqttError:
                logger.warning("MQTT publish failed, reconnecting once and retrying")
                await self._reconnect()
                await self._client.publish(topic, payload, qos=qos, retain=retain)

    async def _reconnect(self) -> None:
        try:
            await self._client.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        await self.start()


mqtt_publisher = MqttPublisher()
