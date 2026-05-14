"""
BASIS — Authenticated Telemetry WebSocket Endpoint
Stage 9: Identity-aware telemetry gateway for OT/BAS environments.

GET /ws/telemetry?token=<JWT>  (WebSocket upgrade)

Authentication
──────────────
Clients supply their Keycloak access token via the ?token= query parameter.
The server accepts the connection before inspecting the token because browsers
require an accepted WebSocket before custom close codes are readable.

  No token / invalid token / denied  →  close 4000
  Token expired mid-session          →  close 4001 (server-initiated)
  Normal client disconnect           →  close 1000 / 1001

Authorization
─────────────
Action: subscribe:telemetry.  Required roles: viewer, operator, admin.
Denied subjects receive a SUBSCRIBE audit event (outcome="denied") and are
closed with code 4000.

Session lifecycle
─────────────────
  1. Client opens WebSocket with ?token=<JWT>
  2. Server calls ws.accept() (required before custom close codes)
  3. Token validated → malformed / expired / unauthorized → close 4000
                        SUBSCRIBE audit event (outcome="denied")
  4. TelemetrySession constructed from JWT claims
  5. Broadcaster registers session, sends full snapshot to client
  6. SUBSCRIBE audit event emitted (outcome="allowed")
  7. Background task monitors token expiry, closes with code 4001 at exp
  8. Connection loop runs until disconnect (any reason)
  9. Expiry task cancelled, broadcaster unregistered
 10. DISCONNECT audit event emitted with session_duration_seconds and disconnect_reason

Audit events
────────────
  action="subscribe:telemetry"   outcome="denied"       — auth/authz failure
  action="subscribe:telemetry"   outcome="allowed"      — session established
  action="disconnect:telemetry"  outcome="disconnected" — session ended

Wire format (unchanged from Stage 3)
─────────────────────────────────────
  On connect:  {"type": "snapshot", "data": {topic: payload, ...}}
  On update:   {"type": "update",   "topic": "...", "data": {...}}
  Client sends: nothing (read-only stream)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from audit import audit_logger
from auth import validate_token
from domain.events import AuditEvent
from domain.session import TelemetrySession
from domain.subject import subject_from_jwt
from policy import actions, engine as policy_engine
from ws_manager import broadcaster

log = logging.getLogger("basis.telemetry")
router = APIRouter(tags=["telemetry"])

# Sentinel subject identifier used in audit events when no valid token was presented
_ANON = "anonymous"


def _ws_origin(ws: WebSocket) -> str:
    """Extract the Origin header from the WebSocket upgrade request, or '(none)'."""
    return dict(ws.headers).get("origin", "(none)")


def _ws_host(ws: WebSocket) -> str:
    """Extract the Host header from the WebSocket upgrade request."""
    return dict(ws.headers).get("host", "(none)")


async def _expiry_watcher(ws: WebSocket, session: TelemetrySession) -> None:
    """
    Background task: sleep until the session token expires, then close the connection.

    Sends WS close code 4001 to signal the client that a token refresh is needed.
    The frontend handles 4001 by calling refreshToken() and reconnecting immediately
    (no backoff delay — this is an expected, handled condition, not a server fault).

    If the connection closes before the token expires (the normal case), this task
    is cancelled by the handler's finally block and exits silently.
    """
    secs = session.seconds_until_expiry
    if secs > 0:
        log.debug(
            "Expiry watcher started — session=%s expires in %.0fs",
            session.session_id, secs,
        )
        await asyncio.sleep(secs)

    # If we reach here, either the token just expired or was already expired.
    # Try to close cleanly; the connection may already be gone.
    try:
        await ws.close(code=4001)
        log.info(
            "Token expired — closed session=%s subject='%s' (code 4001)",
            session.session_id, session.subject_name,
        )
    except Exception:
        pass  # Connection already closed — silently exit


@router.websocket("/ws/telemetry")
async def ws_telemetry(
    ws: WebSocket,
    token: Optional[str] = Query(default=None),
) -> None:
    """
    Authenticated WebSocket endpoint for live OT telemetry streaming.

    Requires a valid Keycloak access token in the ?token= query parameter.
    The subject must hold the subscribe:telemetry action (viewer, operator, or admin).

    See module docstring for full lifecycle, audit events, and wire format.
    """
    # ── Step 1: Accept the connection ─────────────────────────────────────────
    # Must happen before we can send close codes that browsers can read.
    # This means we briefly accept then immediately close on auth failure —
    # that is the correct behavior for WebSocket authentication.
    await ws.accept()

    # ── Step 2: Resolve client IP and log connection attempt ─────────────────
    client_ip: Optional[str] = None
    headers = dict(ws.headers)
    if "x-forwarded-for" in headers:
        # Reverse proxy / Codespaces forwarding — take the leftmost (client) IP
        client_ip = headers["x-forwarded-for"].split(",")[0].strip()
    elif ws.client:
        client_ip = ws.client.host

    origin = _ws_origin(ws)
    host   = _ws_host(ws)
    log.info(
        "WS connect — ip=%s  origin=%s  host=%s  token=%s",
        client_ip, origin, host, "present" if token else "MISSING",
    )

    # ── Step 3: Validate token ────────────────────────────────────────────────
    if not token:
        log.warning(
            "WS rejected (4000) — no token provided  origin=%s  ip=%s",
            origin, client_ip,
        )
        await audit_logger.record(AuditEvent(
            subject_id=_ANON,
            subject_name=_ANON,
            subject_roles=[],
            action=actions.SUBSCRIBE_TELEMETRY,
            endpoint="WS /ws/telemetry",
            outcome="denied",
            reason="No token provided.",
        ))
        await ws.close(code=4000)
        return

    try:
        payload = await validate_token(token)
    except Exception as exc:
        # validate_token raises HTTPException; log its detail so the exact reason
        # (issuer mismatch, expired, bad signature, ...) is visible in logs.
        detail = getattr(exc, "detail", str(exc))
        log.warning(
            "WS rejected (4000) — token validation failed  origin=%s  ip=%s: %s",
            origin, client_ip, detail,
        )
        await audit_logger.record(AuditEvent(
            subject_id=_ANON,
            subject_name=_ANON,
            subject_roles=[],
            action=actions.SUBSCRIBE_TELEMETRY,
            endpoint="WS /ws/telemetry",
            outcome="denied",
            reason=f"Token validation failed: {detail}",
        ))
        await ws.close(code=4000)
        return

    # ── Step 4: Authorize ─────────────────────────────────────────────────────
    subject = subject_from_jwt(payload)
    result  = policy_engine.evaluate(subject, actions.SUBSCRIBE_TELEMETRY)

    if not result.allowed:
        log.warning(
            "WS rejected (4000) — authorization denied  subject='%s'  roles=%s  "
            "action='%s'  reason='%s'  origin=%s",
            subject.name, subject.roles, actions.SUBSCRIBE_TELEMETRY,
            result.reason, origin,
        )
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action=actions.SUBSCRIBE_TELEMETRY,
            endpoint="WS /ws/telemetry",
            outcome="denied",
            reason=result.reason,
        ))
        await ws.close(code=4000)
        return

    # ── Steps 5–8: Session setup ──────────────────────────────────────────────
    # Wrapped in try/except to guarantee a clean 4000 close on any unexpected
    # error here. Without this guard, an exception in broadcaster.connect or
    # create_task escapes the function entirely — FastAPI then closes the socket
    # with a non-application code (1011 or 1006) which the frontend interprets
    # as a transient network failure and enters an infinite reconnect loop.
    try:
        # Step 5: Build TelemetrySession
        iat = payload.get("iat", 0)
        exp = payload.get("exp", 0)
        session = TelemetrySession(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            issued_at=datetime.fromtimestamp(iat, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
            client_ip=client_ip,
            # zone: None — populated in a future stage via ?zone= query param
        )

        # Step 6: Register with broadcaster (sends snapshot)
        await broadcaster.connect(ws, session)

        # Step 7: Emit SUBSCRIBE allowed audit event
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action=actions.SUBSCRIBE_TELEMETRY,
            endpoint="WS /ws/telemetry",
            outcome="allowed",
            detail={
                "session_id":  session.session_id,
                "client_ip":   client_ip,
                "origin":      origin,
                "zone":        session.zone,
                "expires_at":  session.expires_at.isoformat(),
            },
        ))

        log.info(
            "WS session started — session=%s  subject='%s'  roles=%s  "
            "origin=%s  ip=%s",
            session.session_id, subject.name, subject.roles, origin, client_ip,
        )

        # Step 8: Start token expiry watcher
        expiry_task = asyncio.create_task(
            _expiry_watcher(ws, session),
            name=f"expiry-{session.session_id}",
        )

    except Exception as exc:
        log.error(
            "WS session setup failed — subject='%s'  origin=%s  ip=%s: %s",
            subject.name, origin, client_ip, exc,
            exc_info=True,
        )
        await ws.close(code=4000)
        return

    # Track wall-clock session duration for the DISCONNECT audit event
    connected_at      = datetime.now(timezone.utc)
    disconnect_reason = "client_disconnect"

    # ── Step 9: Read loop ─────────────────────────────────────────────────────
    try:
        while True:
            # We only send — never receive. await receive_text() keeps the
            # connection alive and raises WebSocketDisconnect on client close.
            await ws.receive_text()

    except WebSocketDisconnect as exc:
        code = getattr(exc, "code", 1000)
        if code == 4001:
            disconnect_reason = "token_expired"
        else:
            disconnect_reason = "client_disconnect"
        log.info(
            "WS disconnect — session=%s  code=%s  reason=%s",
            session.session_id, code, disconnect_reason,
        )

    except Exception as exc:
        disconnect_reason = "error"
        log.warning(
            "WS closed with unexpected error — session=%s: %s",
            session.session_id, exc,
        )

    finally:
        # Cancel expiry watcher — it must not outlive the connection
        expiry_task.cancel()
        broadcaster.disconnect(ws)

        # ── Emit DISCONNECT audit event ───────────────────────────────────────
        session_duration = (datetime.now(timezone.utc) - connected_at).total_seconds()
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action=actions.DISCONNECT_TELEMETRY,
            endpoint="WS /ws/telemetry",
            outcome="disconnected",
            detail={
                "session_id":               session.session_id,
                "disconnect_reason":        disconnect_reason,
                "session_duration_seconds": round(session_duration, 1),
            },
        ))

        log.info(
            "WS session ended — session=%s  subject='%s'  duration=%.1fs  reason=%s",
            session.session_id, subject.name, session_duration, disconnect_reason,
        )
