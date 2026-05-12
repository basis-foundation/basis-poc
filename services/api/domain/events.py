"""
BASIS — Domain Event Models
Stage 5: AuditEvent introduced.
Stage 7: subject_type field added to AuditEvent — populated from Subject.type.value.
Stage 7b: TelemetryEvent and CommandEvent introduced as normalized internal event models.
          These represent the canonical domain representation of inbound telemetry and
          outbound commands. They are internal only — the WebSocket wire format (topic +
          raw payload dict) and MQTT payload format are both unchanged.
Stage 8: resource_type field added to AuditEvent — populated from Resource.type.value.
         Resources are now first-class audit fields rather than ad hoc strings.

Design constraint: this module has NO imports from other BASIS modules.
It is the base of the import graph. Everything else may import from here;
nothing here imports from adapters, routers, auth, audit, policy, or domain/resource.

Event taxonomy
──────────────
  AuditEvent      — authorization decision or command dispatch outcome.
                    Written to the audit log by require_action() and the controls router.
  TelemetryEvent  — normalized representation of an inbound MQTT telemetry message.
                    Constructed in the MQTT subscriber after JSON parse; passed internally
                    to logging and enrichment. The broadcaster still receives the raw
                    payload dict for WebSocket delivery (wire format unchanged).
  CommandEvent    — normalized representation of an outbound HVAC command.
                    Constructed in the controls router before publish_command(); carries
                    the typed subject, resource, and payload in one place. The publisher
                    still receives the same dict payload (MQTT wire format unchanged).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """
    Normalized record of an authorization decision or command dispatch.

    Action types recorded in Stage 8:
      policy action name  — e.g. "write:hvac:setpoint" — recorded by require_action()
                            for every protected endpoint call (allowed and denied).
      "command_dispatch"  — recorded by the controls router after MQTT publish attempt,
                            capturing the command parameters and delivery outcome.

    Stage 8 adds resource_type alongside resource_id, making the targeted resource
    unambiguous in the audit trail without parsing the resource_id string.

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
    action:        str                   # policy action name or "command_dispatch"
    resource_id:   Optional[str] = None  # normalized resource ID — "hvac:main"
    resource_type: Optional[str] = None  # ResourceType value — "hvac", "sensor", ...
    endpoint:      Optional[str] = None  # "POST /api/controls/hvac/main/setpoint"

    # ── Outcome ───────────────────────────────────────────────────────────────
    outcome: str                   # "allowed" | "denied" | "error"
    reason:  Optional[str] = None  # human-readable detail

    # ── Extra context ─────────────────────────────────────────────────────────
    detail: dict = {}  # command parameters, error info — arbitrary key/value


class TelemetryEvent(BaseModel):
    """
    Normalized internal representation of a single inbound MQTT telemetry message.

    Constructed in adapters/mqtt/subscriber.py immediately after JSON parse.
    The subscriber then still calls broadcaster.broadcast(topic, payload) unchanged —
    this model is for internal enrichment, logging, and future routing logic only.

    Fields
    ──────
    event_type    always "telemetry" — distinguishes from CommandEvent at call sites
                  that handle both types.
    resource_id   normalized resource ID resolved from TOPIC_TO_RESOURCE lookup
                  e.g. "hvac:main", "sensor:co2". Empty string if topic is unknown.
    resource_type ResourceType value derived from the resource_id prefix e.g. "hvac",
                  "sensor". Empty string if topic is unknown.
    source        the raw MQTT topic string e.g. "basis/hvac/main/telemetry".
    timestamp     taken from the payload "timestamp" field if present; falls back to
                  ingestion time (datetime.now(timezone.utc)).
    payload       the original telemetry payload dict, forwarded unchanged to the
                  WebSocket broadcaster.
    correlation_id reserved for future distributed-trace correlation. None in Stage 7b.
    """

    event_type:     str = "telemetry"
    resource_id:    str                   # "hvac:main", "sensor:co2" — may be "" if unknown
    resource_type:  str                   # "hvac", "sensor" — may be "" if unknown
    source:         str                   # MQTT topic
    timestamp:      datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload:        dict                  # original telemetry payload — forwarded to WS
    correlation_id: Optional[str] = None


class CommandEvent(BaseModel):
    """
    Normalized internal representation of an outbound HVAC setpoint command.

    Constructed in routers/controls.py before calling publish_command().
    Provides a single typed object capturing all context about a command:
    who issued it, what resource it targets, what action it represents, and
    what payload will be forwarded to the simulator via MQTT.

    The MQTT publisher still receives command_event.payload unchanged —
    the MQTT wire format is not affected.

    Fields
    ──────
    command_type  short descriptor of the command kind e.g. "hvac:setpoint".
    resource_id   normalized resource ID e.g. "hvac:main".
    resource_type ResourceType value e.g. "hvac".
    subject_id    JWT sub claim (stable across sessions).
    subject_name  preferred_username (human-readable).
    action        named policy action e.g. "write:hvac:setpoint".
    payload       dict forwarded verbatim to publish_command() and the simulator.
    timestamp     time the command was constructed in the handler.
    correlation_id reserved for future distributed-trace correlation. None in Stage 7b.
    """

    command_type:   str                   # "hvac:setpoint"
    resource_id:    str                   # "hvac:main"
    resource_type:  str                   # "hvac"
    subject_id:     str                   # JWT sub claim
    subject_name:   str                   # preferred_username
    action:         str                   # "write:hvac:setpoint"
    payload:        dict                  # MQTT payload forwarded to simulator
    timestamp:      datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None
