"""
Basis Foundation — WebSocket Telemetry Endpoint

GET /ws/telemetry  (WebSocket upgrade)

Protocol:
  On connect  → server sends: {"type": "snapshot", "data": {topic: payload, ...}}
  On update   → server sends: {"type": "update",   "topic": "...", "data": {...}}
  Client sends: nothing in Stage 3 (read-only telemetry stream)

Authentication note:
  Stage 3: unauthenticated — any browser can subscribe to telemetry.
  Stage 4 will add token validation via ?token= query parameter before
  the WebSocket handshake is accepted.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_manager import broadcaster

log = logging.getLogger("basis.telemetry")
router = APIRouter(tags=["telemetry"])


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    """
    WebSocket endpoint for live telemetry streaming.

    Clients receive a JSON snapshot of all known telemetry on connect,
    followed by incremental updates as MQTT messages arrive.
    """
    await broadcaster.connect(ws)
    try:
        # Keep the connection alive — we only send, never receive in Stage 3
        while True:
            # Await any client message (or disconnect signal)
            # Using receive_text() so we can detect disconnects cleanly
            await ws.receive_text()
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected normally")
    except Exception as exc:
        log.debug("WebSocket closed unexpectedly: %s", exc)
    finally:
        broadcaster.disconnect(ws)
