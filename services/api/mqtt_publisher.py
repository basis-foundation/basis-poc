"""
Basis Foundation — MQTT Command Publisher

Publishes a single message and disconnects — appropriate for infrequent,
human-driven control commands. Uses paho.mqtt.publish.single() wrapped in
asyncio.to_thread() so it doesn't block FastAPI's event loop.

Why not aiomqtt here:
  aiomqtt is designed as a long-lived async context manager (ideal for the
  subscriber). For fire-and-forget command publishing, paho's publish.single()
  is simpler — it opens a connection, publishes, and closes in one call.
"""

import asyncio
import json
import logging
import os

import paho.mqtt.publish as mqtt_publish

log = logging.getLogger("basis.publisher")

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))


async def publish_command(topic: str, payload: dict, qos: int = 1) -> None:
    """
    Publish a JSON payload to an MQTT topic.

    Runs the blocking paho call in a thread-pool executor so FastAPI's
    async event loop is never blocked.

    Raises RuntimeError if the broker is unreachable.
    """
    serialised = json.dumps(payload, default=str)
    log.info("Publishing to %s  payload=%s", topic, serialised)

    try:
        await asyncio.to_thread(
            mqtt_publish.single,
            topic,
            payload=serialised,
            qos=qos,
            retain=False,
            hostname=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
        )
        log.info("Published OK → %s", topic)
    except Exception as exc:
        log.error("MQTT publish failed on %s: %s", topic, exc)
        raise RuntimeError(f"Could not reach MQTT broker: {exc}") from exc
