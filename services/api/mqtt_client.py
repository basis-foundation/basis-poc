"""
Basis Foundation — MQTT Subscriber (FastAPI side)

Runs as a persistent asyncio background task started during FastAPI startup.
Subscribes to all basis/# topics, parses payloads, and forwards to the
WebSocket broadcaster.

Reconnect strategy:
  - Uses aiomqtt's async context manager for clean session lifecycle
  - On any MqttError, waits RETRY_DELAY_SECONDS and reconnects
  - On asyncio.CancelledError (shutdown), exits cleanly
"""

import asyncio
import json
import logging
import os

import aiomqtt

from ws_manager import broadcaster

log = logging.getLogger("basis.mqtt")

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
SUBSCRIBE_TOPIC  = "basis/#"   # wildcard: HVAC + all sensors
RETRY_DELAY      = 5           # seconds between reconnect attempts

# Topics we expect and care about — used for logging clarity
KNOWN_TOPICS = {
    "basis/hvac/main/telemetry",
    "basis/sensors/co2/telemetry",
    "basis/sensors/occupancy/telemetry",
    "basis/simulator/heartbeat",
    "basis/simulator/status",
}


async def _handle_message(topic: str, raw: bytes) -> None:
    """Parse a raw MQTT payload and broadcast it to WebSocket clients."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("Unparseable MQTT message on %s: %s", topic, exc)
        return

    if topic not in KNOWN_TOPICS:
        log.debug("Received message on unexpected topic: %s", topic)

    log.debug("MQTT → %s  clients=%d", topic, broadcaster.client_count)
    await broadcaster.broadcast(topic, payload)


async def mqtt_listener() -> None:
    """
    Persistent background task.
    Connects to Mosquitto, subscribes to basis/#, and processes messages.
    Automatically reconnects on any broker-level error.
    """
    log.info(
        "MQTT listener starting — broker=%s:%d  topic=%s",
        MQTT_BROKER_HOST, MQTT_BROKER_PORT, SUBSCRIBE_TOPIC,
    )

    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_BROKER_HOST,
                port=MQTT_BROKER_PORT,
                identifier="basis-api",
                keepalive=30,
            ) as client:
                await client.subscribe(SUBSCRIBE_TOPIC, qos=0)
                log.info(
                    "MQTT subscribed to '%s' on %s:%d",
                    SUBSCRIBE_TOPIC, MQTT_BROKER_HOST, MQTT_BROKER_PORT,
                )

                async for message in client.messages:
                    topic   = str(message.topic)
                    payload = bytes(message.payload)
                    await _handle_message(topic, payload)

        except aiomqtt.MqttError as exc:
            log.warning(
                "MQTT broker error: %s — reconnecting in %ds",
                exc, RETRY_DELAY,
            )
            await asyncio.sleep(RETRY_DELAY)

        except asyncio.CancelledError:
            log.info("MQTT listener cancelled — shutting down cleanly")
            break

        except Exception as exc:
            log.error("Unexpected error in MQTT listener: %s", exc, exc_info=True)
            await asyncio.sleep(RETRY_DELAY)
