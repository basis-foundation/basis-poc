"""
BASIS — Telemetry Session Model
Stage 9: Identity-bound WebSocket session for authenticated telemetry streaming.

A TelemetrySession is created for each authenticated WebSocket connection.
It binds the authenticated identity to the session for the lifetime of the
connection, providing:
  - Audit trail: SUBSCRIBE and DISCONNECT events carry session_id as a stable
                 cross-reference between the two audit records.
  - Token expiry enforcement: expires_at drives the background watcher that
                              closes the connection with code 4001.
  - Authorization extension point: the zone field is reserved for Stage 10+
                                   per-zone subscription filtering and policy.
  - Operator accountability: every telemetry session is traceable to a specific
                             subject identity and token issuance event.

Why a typed model, not a raw dict?
───────────────────────────────────
The session carries security-relevant state (token expiry, subject identity,
authorization context). A Pydantic model makes the expiry check explicit and
immutable, the authorization hook visible to future contributors, and the
serialization to audit detail dicts reliable. A plain dict is implicit and
fragile against future field additions.

Import constraint
──────────────────
This module has NO imports from other BASIS modules. It is part of domain/,
which is the base of the import graph. Only stdlib and Pydantic are allowed.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class TelemetrySession(BaseModel):
    """
    Represents a single authenticated WebSocket telemetry session.

    Created when a client successfully authenticates via ?token= query parameter
    and the PolicyEngine allows subscribe:telemetry for their subject.

    Destroyed — and a DISCONNECT audit event emitted — when the connection closes
    for any reason: normal client disconnect, token expiry (code 4001), server
    shutdown, or network error.

    All identity fields are sourced from the JWT payload at connection time and
    frozen thereafter. Session identity cannot be mutated after creation.
    """

    model_config = {"frozen": True}

    # ── Session identity ──────────────────────────────────────────────────────
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description=(
            "Unique identifier for this WebSocket session. "
            "Appears in both the SUBSCRIBE and DISCONNECT audit events as a "
            "stable cross-reference. Not the JWT sub — one subject may have "
            "multiple concurrent sessions."
        ),
    )

    # ── Subject fields (from JWT at connection time) ──────────────────────────
    subject_id:    str        # JWT sub claim — stable across token refreshes
    subject_name:  str        # JWT preferred_username — human-readable identity
    subject_type:  str        # SubjectType.value — e.g. "human"
    subject_roles: list[str]  # Realm roles held at connection time

    # ── Token validity window ─────────────────────────────────────────────────
    # Derived from JWT iat and exp claims at connection time.
    # is_expired uses these to enforce expiry without re-fetching JWKS on every tick.
    issued_at:  datetime   # datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    expires_at: datetime   # datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    # ── Connection metadata ───────────────────────────────────────────────────
    client_ip: Optional[str] = None
    # Source IP — from X-Forwarded-For (first entry) or WebSocket client host.
    # Recorded in the SUBSCRIBE audit event for operator accountability.

    # ── Future authorization extension point ──────────────────────────────────
    # Stage 10+ can populate this from the URL query parameter, e.g.:
    #   /ws/telemetry?token=<JWT>&zone=north
    # Once populated, the policy engine can gate per-zone subscriptions and the
    # broadcaster can filter updates to only the relevant zone's topics.
    # Left as None in Stage 9 — the field is part of the design contract, not
    # a placeholder. Its absence here makes the extension path explicit.
    zone: Optional[str] = None

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        """True if the token's exp claim has passed."""
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def seconds_until_expiry(self) -> float:
        """
        Seconds remaining until the token expires.
        Returns 0.0 if already expired.
        Used by _expiry_watcher() in routers/telemetry.py to schedule ws.close(4001).
        """
        delta = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
