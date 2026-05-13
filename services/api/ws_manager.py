"""
Basis Foundation — WebSocket Broadcast Manager
Stage 9: Sessions are now identity-bound. Each connected WebSocket is associated
         with a TelemetrySession carrying the authenticated subject identity,
         token expiry window, client IP, and the zone extension hook.

Changes from Stage 3:
  - _connections: list[WebSocket]  →  _sessions: dict[WebSocket, TelemetrySession]
  - connect(ws) → connect(ws, session): caller builds TelemetrySession before connecting
  - disconnect(ws) → returns TelemetrySession | None: caller uses session for audit trail

Wire format is unchanged. Clients receive the same snapshot and update messages
as in Stage 3. Authentication is a gateway concern — the broadcaster stays clean.
"""

import json
import logging
from typing import Optional

from fastapi import WebSocket

from domain.session import TelemetrySession

log = logging.getLogger("basis.ws")


class TelemetryBroadcaster:
    def __init__(self) -> None:
        # Active sessions keyed by WebSocket.
        # asyncio is single-threaded — no lock is needed.
        self._sessions: dict[WebSocket, TelemetrySession] = {}

        # Latest known payload per MQTT topic — used for snapshot on connect.
        # Populated by broadcast() on every inbound MQTT message.
        self._snapshot: dict[str, dict] = {}

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self, ws: WebSocket, session: TelemetrySession) -> None:
        """
        Register an already-accepted WebSocket and immediately send the current snapshot.

        The caller is responsible for:
          - Calling ws.accept() before this method (required for custom close codes)
          - Building the TelemetrySession from the validated JWT payload
          - Emitting the SUBSCRIBE audit event after this returns

        The WebSocket must be accepted before calling connect().
        """
        self._sessions[ws] = session
        log.info(
            "WS registered — session=%s subject='%s' clients=%d",
            session.session_id, session.subject_name, len(self._sessions),
        )

        snapshot_msg = {"type": "snapshot", "data": self._snapshot}
        await self._send_one(ws, snapshot_msg)

    def disconnect(self, ws: WebSocket) -> Optional[TelemetrySession]:
        """
        Remove a WebSocket from the active session map.

        Returns the TelemetrySession that was associated with the connection,
        or None if the WebSocket was not registered (e.g., disconnected before
        authentication completed). The caller uses the returned session to emit
        the DISCONNECT audit event with session identity and duration.
        """
        session = self._sessions.pop(ws, None)
        if session:
            log.info(
                "WS removed — session=%s subject='%s' clients=%d",
                session.session_id, session.subject_name, len(self._sessions),
            )
        return session

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast(self, topic: str, payload: dict) -> None:
        """
        Store the latest payload for this topic and push an update to all clients.
        Called by the MQTT listener on every inbound message.

        Wire format (unchanged from Stage 3):
          {"type": "update", "topic": "<mqtt_topic>", "data": <payload_dict>}
        """
        self._snapshot[topic] = payload
        if not self._sessions:
            return

        message = {"type": "update", "topic": topic, "data": payload}
        await self._broadcast_all(message)

    async def _broadcast_all(self, message: dict) -> None:
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for ws in list(self._sessions):
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
        return len(self._sessions)

    def get_session(self, ws: WebSocket) -> Optional[TelemetrySession]:
        """Return the TelemetrySession for a connected WebSocket, or None."""
        return self._sessions.get(ws)


# Module-level singleton — imported by the MQTT subscriber and the telemetry router
broadcaster = TelemetryBroadcaster()
