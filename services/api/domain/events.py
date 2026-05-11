"""
BASIS — Domain Event Models
Stage 5: AuditEvent introduced.
Stage 7: subject_type field added to AuditEvent — populated from Subject.type.value.

Design constraint: this module has NO imports from other BASIS modules.
It is the base of the import graph. Everything else may import from here;
nothing here imports from adapters, routers, auth, audit, or policy.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """
    Normalized record of an authorization decision or command dispatch.

    Two action types are populated in Stage 5:
      "api_access"       — recorded by require_role() for every protected endpoint call,
                           both allowed and denied outcomes.
      "command_dispatch" — recorded by the controls router after MQTT publish attempt,
                           capturing the command parameters and delivery outcome.

    Fields marked as optional will be populated by later stages as the domain
    model is extended. No existing field will be removed — only added.
    """

    # ── Envelope ──────────────────────────────────────────────────────────────
    event_id:  str      = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Subject — who performed the action ────────────────────────────────────
    subject_id:    str        # JWT sub claim (stable across sessions)
    subject_name:  str        # preferred_username (human-readable)
    subject_type:  str = "human"  # SubjectType value — "human" until Stage 7 non-human paths
    subject_roles: list[str]  # realm_access.roles at time of request

    # ── Action — what they did ────────────────────────────────────────────────
    action:      str                   # "api_access" | "command_dispatch"
    resource_id: Optional[str] = None  # "hvac:main" — populated for command_dispatch
    endpoint:    Optional[str] = None  # "POST /api/controls/hvac/main/setpoint"

    # ── Outcome ───────────────────────────────────────────────────────────────
    outcome: str                   # "allowed" | "denied" | "error"
    reason:  Optional[str] = None  # human-readable detail

    # ── Extra context ─────────────────────────────────────────────────────────
    detail: dict = {}  # command parameters, error info — arbitrary key/value
