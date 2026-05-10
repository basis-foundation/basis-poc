"""
Basis Foundation — WebSocket Broadcast Manager

Singleton that:
  - Tracks all connected WebSocket clients
  - Maintains a snapshot of the latest telemetry per topic
  - Sends a full snapshot immediately on new connection
  - Fans out MQTT-derived updates to all live connections
"""

import json
import logging
from fastapi import WebSocket

log = logging.getLogger("basis.ws")


class TelemetryBroadcaster:
    def __init__(self) -> None:
        # Active WebSocket connections (asyncio is single-threaded; no lock needed)
        self._connections: list[WebSocket] = []
        # Latest known payload per MQTT topic — used for snapshot on connect
        self._snapshot: dict[str, dict] = {}

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection and immediately send the current snapshot."""
        await ws.accept()
        self._connections.append(ws)
        log.info("WebSocket connected — %d client(s) active", len(self._connections))

        if self._snapshot:
            await self._send_one(ws, {"type": "snapshot", "data": self._snapshot})
        else:
            # No telemetry received yet — tell the client to expect data soon
            await self._send_one(ws, {"type": "snapshot", "data": {}})

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from the active list (call from finally block)."""
        try:
            self._connections.remove(ws)
        except ValueError:
            pass  # already gone
        log.info("WebSocket disconnected — %d client(s) active", len(self._connections))

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast(self, topic: str, payload: dict) -> None:
        """
        Store the latest payload for this topic and push an update to all clients.
        Called by the MQTT listener on every inbound message.
        """
        self._snapshot[topic] = payload
        if not self._connections:
            return

        message = {"type": "update", "topic": topic, "data": payload}
        await self._broadcast_all(message)

    async def _broadcast_all(self, message: dict) -> None:
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception as exc:
                log.debug("WebSocket send failed (%s) — marking for removal", exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _send_one(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_text(json.dumps(message, default=str))
        except Exception as exc:
            log.warning("Failed to send snapshot to new client: %s", exc)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Module-level singleton — imported by mqtt_client and the telemetry router
broadcaster = TelemetryBroadcaster()
