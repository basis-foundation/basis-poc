"""
BASIS — MQTT Publisher Adapter

Publishes a single message and disconnects. Appropriate for infrequent,
human-driven control commands.

Uses paho.mqtt.publish.single() wrapped in asyncio.to_thread() to avoid
blocking FastAPI's event loop.

Authentication (Stage 6):
  Reads MQTT_USERNAME and MQTT_PASSWORD from environment. If set, every
  publish call authenticates with those credentials. If unset, publishes
  anonymously (development only — requires Mosquitto in anonymous mode).

Why paho publish.single here instead of aiomqtt:
  aiomqtt is designed as a long-lived async context manager — ideal for the
  subscriber. For fire-and-forget command publishing, paho's publish.single()
  is cleaner: it opens a connection, publishes, and closes in one call.
  Commands are human-driven and infrequent, so connection overhead is fine.
"""

import asyncio
import json
import logging
import os

import paho.mqtt.publish as mqtt_publish

log = logging.getLogger("basis.mqtt.publisher")

# ── Configuration ─────────────────────────────────────────────────────────────
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME    = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD    = os.getenv("MQTT_PASSWORD", "")

# Build auth dict once at import time.
# paho publish.single accepts auth=None (anonymous) or auth={'username':..., 'password':...}
_MQTT_AUTH = (
    {"username": MQTT_USERNAME, "password": MQTT_PASSWORD}
    if MQTT_USERNAME
    else None
)

if _MQTT_AUTH:
    log.info("MQTT publisher identity: username=%s", MQTT_USERNAME)
else:
    log.warning(
        "MQTT publisher running WITHOUT credentials (anonymous). "
        "Set MQTT_USERNAME and MQTT_PASSWORD to enable authenticated publishing."
    )


async def publish_command(topic: str, payload: dict, qos: int = 1) -> None:
    """
    Publish a JSON payload to an MQTT topic.

    Runs the blocking paho call in a thread-pool executor so FastAPI's
    async event loop is never blocked.

    Raises RuntimeError if the broker is unreachable or rejects the connection.
    The controls router catches RuntimeError and returns HTTP 503.
    """
    serialised = json.dumps(payload, default=str)
    auth_desc  = f"user={MQTT_USERNAME}" if MQTT_USERNAME else "anonymous"
    log.info("Publishing to %s  auth=%s  payload=%s", topic, auth_desc, serialised)

    try:
        await asyncio.to_thread(
            mqtt_publish.single,
            topic,
            payload=serialised,
            qos=qos,
            retain=False,
            hostname=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            auth=_MQTT_AUTH,
        )
        log.info("Published OK → %s", topic)
    except Exception as exc:
        exc_str = str(exc)
        if "not authorized" in exc_str.lower() or "bad username" in exc_str.lower():
            log.error(
                "MQTT publish rejected — authentication failed. "
                "MQTT_USERNAME=%r  broker=%s:%d",
                MQTT_USERNAME or "(not set)", MQTT_BROKER_HOST, MQTT_BROKER_PORT,
            )
        else:
            log.error("MQTT publish failed on %s: %s", topic, exc)
        raise RuntimeError(f"Could not reach MQTT broker: {exc}") from exc
