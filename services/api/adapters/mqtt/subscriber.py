"""
BASIS — MQTT Subscriber Adapter

Runs as a persistent asyncio background task started during FastAPI startup.
Subscribes to all basis/# topics, parses payloads, and forwards to the
WebSocket broadcaster.

Authentication (Stage 6):
  Reads MQTT_USERNAME and MQTT_PASSWORD from environment. If both are set,
  the connection is authenticated. If neither is set, the connection is
  anonymous (used only when Mosquitto is still in anonymous mode during
  development transitions).

  When Mosquitto enforces authentication (allow_anonymous false), these env
  vars are required. A missing or wrong credential causes MQTT rc=4/rc=5
  which is logged with a clear diagnostic message before retrying.

Reconnect strategy:
  - On any MqttError, waits RETRY_DELAY seconds and reconnects.
  - On asyncio.CancelledError (shutdown), exits cleanly.
  - Auth failures are logged with explicit credential guidance before retrying.
"""

import asyncio
import json
import logging
import os

import aiomqtt

from adapters.mqtt.topics import SUBSCRIBE_ALL, KNOWN_TOPICS
from ws_manager import broadcaster

log = logging.getLogger("basis.mqtt.subscriber")

# ── Configuration ─────────────────────────────────────────────────────────────
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "mosquitto")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME    = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD    = os.getenv("MQTT_PASSWORD", "")

RETRY_DELAY = 5  # seconds between reconnect attempts

# ── Startup identity log ──────────────────────────────────────────────────────
# Logged at module import time so it appears immediately in container startup.
if MQTT_USERNAME:
    log.info(
        "MQTT subscriber identity: username=%s  broker=%s:%d",
        MQTT_USERNAME, MQTT_BROKER_HOST, MQTT_BROKER_PORT,
    )
else:
    log.warning(
        "MQTT subscriber running WITHOUT credentials (anonymous). "
        "Set MQTT_USERNAME and MQTT_PASSWORD to enable authenticated connections."
    )


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
    auth_desc = f"user={MQTT_USERNAME}" if MQTT_USERNAME else "anonymous"
    log.info(
        "MQTT listener starting — broker=%s:%d  topic=%s  auth=%s",
        MQTT_BROKER_HOST, MQTT_BROKER_PORT, SUBSCRIBE_ALL, auth_desc,
    )

    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_BROKER_HOST,
                port=MQTT_BROKER_PORT,
                identifier="basis-api-subscriber",
                keepalive=30,
                username=MQTT_USERNAME or None,
                password=MQTT_PASSWORD or None,
            ) as client:
                await client.subscribe(SUBSCRIBE_ALL, qos=0)
                log.info(
                    "MQTT connected and subscribed — broker=%s:%d  topic=%s  auth=%s",
                    MQTT_BROKER_HOST, MQTT_BROKER_PORT, SUBSCRIBE_ALL, auth_desc,
                )

                async for message in client.messages:
                    topic   = str(message.topic)
                    payload = bytes(message.payload)
                    await _handle_message(topic, payload)

        except aiomqtt.MqttError as exc:
            exc_str = str(exc)
            # Detect authentication rejection specifically (rc=4 or rc=5 from broker)
            if any(code in exc_str for code in ("rc=4", "rc=5", "Not authorized", "Bad username")):
                log.error(
                    "MQTT broker rejected credentials (auth failure). "
                    "MQTT_USERNAME=%r — check password and broker password file. "
                    "Retrying in %ds.",
                    MQTT_USERNAME or "(not set)", RETRY_DELAY,
                )
            else:
                log.warning(
                    "MQTT broker error: %s — reconnecting in %ds",
                    exc, RETRY_DELAY,
                )
            await asyncio.sleep(RETRY_DELAY)

        except asyncio.CancelledError:
            log.info("MQTT listener cancelled — shutting down cleanly")
            break

        except Exception as exc:
            log.error(
                "Unexpected error in MQTT listener: %s — retrying in %ds",
                exc, RETRY_DELAY, exc_info=True,
            )
            await asyncio.sleep(RETRY_DELAY)
