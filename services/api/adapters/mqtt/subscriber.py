"""
BASIS — MQTT Subscriber Adapter
Stage 7b:  _handle_message now constructs a TelemetryEvent for telemetry topics.
Stage 10:  MqttAdapter class added — wraps mqtt_listener() in the AdapterBase
           interface so main.py can manage all protocol adapters identically.
          The TelemetryEvent is used for structured internal logging — the
          broadcaster.broadcast() call is unchanged (WebSocket wire format preserved).

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
from datetime import datetime, timezone

import aiomqtt

from adapters.mqtt.topics import SUBSCRIBE_ALL, KNOWN_TOPICS, TOPIC_TO_RESOURCE
from domain.events import TelemetryEvent
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
    """
    Parse a raw MQTT payload, construct a TelemetryEvent for telemetry topics,
    and broadcast the payload to WebSocket clients.

    TelemetryEvent is used for structured internal logging and future routing.
    The broadcaster.broadcast() call is unchanged — WebSocket wire format is
    the raw topic string + original payload dict.
    """
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("Unparseable MQTT message on %s: %s", topic, exc)
        return

    if topic not in KNOWN_TOPICS:
        log.debug("Received message on unexpected topic: %s", topic)

    # ── TelemetryEvent construction (Stage 7b) ────────────────────────────────
    # Only construct for known telemetry topics. Simulator metadata topics
    # (status, heartbeat) are not resource-bearing and skip this path.
    resource_id = TOPIC_TO_RESOURCE.get(topic, "")
    if resource_id:
        # Parse timestamp from payload if present; fall back to ingestion time.
        raw_ts = payload.get("timestamp")
        try:
            ts = datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        # resource_type is the part before the first colon: "hvac:main" → "hvac"
        resource_type = resource_id.split(":")[0] if ":" in resource_id else resource_id

        telemetry_event = TelemetryEvent(
            resource_id=resource_id,
            resource_type=resource_type,
            source=topic,
            timestamp=ts,
            payload=payload,
        )
        log.debug(
            "MQTT telemetry → %s  resource=%s  clients=%d",
            topic, telemetry_event.resource_id, broadcaster.client_count,
        )
    else:
        log.debug("MQTT → %s  clients=%d", topic, broadcaster.client_count)

    # WebSocket broadcast is unchanged — raw topic + original payload dict.
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


# ── AdapterBase wrapper ────────────────────────────────────────────────────────

from adapters.base import AdapterBase  # noqa: E402 — avoids circular import at module top


class MqttAdapter(AdapterBase):
    """
    AdapterBase wrapper for the MQTT subscriber.

    Wraps the existing mqtt_listener() coroutine in the AdapterBase lifecycle
    interface so main.py can manage MqttAdapter and ModbusTcpAdapter identically
    — same start(), same stop(), same log pattern.

    This class does not change how the MQTT listener works. All connection,
    retry, and message-handling logic remains in mqtt_listener() and
    _handle_message(). This is a thin lifecycle shell only.
    """

    adapter_id = "mqtt"
    protocol   = "mqtt"

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(
            mqtt_listener(),
            name=f"adapter-{self.adapter_id}",
        )
        log.info(
            "MqttAdapter started — broker=%s:%d",
            MQTT_BROKER_HOST, MQTT_BROKER_PORT,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("MqttAdapter stopped")
