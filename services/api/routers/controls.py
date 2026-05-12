"""
Basis Foundation — HVAC Control Endpoints
Stage 4: Operator/admin-only setpoint commands published to MQTT.
Stage 5: Command dispatch outcomes recorded to audit log.
Stage 7: Migrated from require_role() to require_action() + Subject.
Stage 7b: CommandEvent constructed before publish_command(). Provides a single
          typed object capturing subject, resource, action, and payload context.
          The MQTT payload dict forwarded to the broker is unchanged.
Stage 8: Resource-aware. Zone validation now driven by the resource registry.
         ResourceIdentifier.build() constructs normalized IDs.
         AuditEvents carry resource_type as a first-class field.

Authorization:
  - viewer  → 403 Forbidden (denied by RoleBasedPolicy, recorded by require_action)
  - operator → allowed
  - admin   → allowed

Authorization + resource flow:
  1. require_action(WRITE_HVAC_SETPOINT) — policy gate, no resource context yet
     (zone is a path param, unknown at dependency setup time)
  2. Handler resolves zone → Resource via registry
     resolve_resource(ResourceIdentifier.build(HVAC, zone))
  3. Unknown resource → 404 (registry-driven, not a hardcoded set)
  4. MQTT publish
  5. command_dispatch AuditEvent with resource_id + resource_type

Validation layers:
  1. Pydantic field constraints  — type, ge/le bounds → 422 Unprocessable Entity
  2. Resource registry lookup    — unknown resource → 404 (replaces VALID_ZONES set)
  3. Simulator validates again   — belt-and-suspenders against broker replay attacks

Audit call sites in this module:
  - command_dispatch/allowed  — MQTT publish succeeded
  - command_dispatch/error    — MQTT publish failed (503 returned to caller)
  The authorization record (action=write:hvac:setpoint) is written by
  require_action() before the handler runs. The command_dispatch record here
  captures the delivery outcome and the targeted resource.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Path
from pydantic import BaseModel, Field

from audit import audit_logger
from auth import require_action
from domain.events import AuditEvent, CommandEvent
from domain.resource import ResourceIdentifier, ResourceType, list_resources, resolve_resource
from domain.subject import Subject
from policy import actions
from adapters.mqtt.publisher import publish_command

router = APIRouter(prefix="/api/controls", tags=["controls"])

COMMAND_TEMP_MIN = 10.0   # °C — absolute floor
COMMAND_TEMP_MAX = 35.0   # °C — absolute ceiling


# ── Request model ─────────────────────────────────────────────────────────────

class SetpointCommand(BaseModel):
    """Payload for an HVAC setpoint change request."""

    target_temperature: float = Field(
        ...,
        ge=COMMAND_TEMP_MIN,
        le=COMMAND_TEMP_MAX,
        description=f"Target temperature in °C ({COMMAND_TEMP_MIN}–{COMMAND_TEMP_MAX})",
        examples=[21.5],
    )


# ── Response model ────────────────────────────────────────────────────────────

class SetpointResponse(BaseModel):
    status: str
    zone: str
    resource_id: str           # normalized resource identifier — "hvac:main"
    resource_type: str         # resource type — "hvac"
    target_temperature: float
    requested_by: str
    mqtt_topic: str
    timestamp: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/hvac/{zone}/setpoint",
    response_model=SetpointResponse,
    summary="Set HVAC zone setpoint",
    description=(
        "Publishes a setpoint command to `basis/hvac/{zone}/command`.\n\n"
        "**Required action:** `write:hvac:setpoint` (operator or admin role).\n\n"
        "Valid zones are those with a registered `hvac:{zone}` resource "
        "(see `GET /api/resources`). The simulator will receive the command "
        "and gradually drive `current_temperature` toward `target_temperature`."
    ),
)
async def set_hvac_setpoint(
    zone: Annotated[
        str,
        Path(description="Zone identifier — must match a registered hvac:{zone} resource"),
    ],
    command: SetpointCommand,
    subject: Subject = Depends(require_action(actions.WRITE_HVAC_SETPOINT)),
) -> SetpointResponse:
    # ── Resource resolution ────────────────────────────────────────────────────
    # Checked after authorization: an unauthorized caller cannot enumerate valid
    # zones by probing for 404 vs 403 responses.
    #
    # The resource registry is the single source of truth for valid HVAC zones.
    # No hardcoded set — add zones by adding resources to domain/resource.py.
    resource_id = ResourceIdentifier.build(ResourceType.HVAC, zone)
    resource    = resolve_resource(resource_id)

    if resource is None:
        known = [r.id for r in list_resources(ResourceType.HVAC)]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown HVAC resource '{resource_id}'. "
                f"Registered HVAC resources: {known}"
            ),
        )

    now   = datetime.now(timezone.utc).isoformat()
    topic = f"basis/hvac/{zone}/command"

    mqtt_payload = {
        "target_temperature": command.target_temperature,
        "requested_by":       subject.name,
        "zone":               zone,
        "timestamp":          now,
    }

    # ── CommandEvent construction (Stage 7b) ──────────────────────────────────
    # Captures the full command context as a typed domain object before dispatch.
    # command_event.payload is the same dict forwarded to publish_command() —
    # the MQTT wire format is unchanged.
    command_event = CommandEvent(
        command_type=f"{resource.type.value}:setpoint",
        resource_id=resource.id,
        resource_type=resource.type.value,
        subject_id=subject.id,
        subject_name=subject.name,
        action=actions.WRITE_HVAC_SETPOINT,
        payload=mqtt_payload,
    )

    try:
        await publish_command(topic, command_event.payload)
    except RuntimeError as exc:
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action="command_dispatch",
            resource_id=resource.id,
            resource_type=resource.type.value,
            endpoint=f"POST /api/controls/hvac/{zone}/setpoint",
            outcome="error",
            reason=str(exc),
            detail={"target_temperature": command.target_temperature},
        ))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Command could not be delivered: {exc}",
        )

    await audit_logger.record(AuditEvent(
        subject_id=subject.id,
        subject_name=subject.name,
        subject_type=subject.type.value,
        subject_roles=subject.roles,
        action="command_dispatch",
        resource_id=resource.id,
        resource_type=resource.type.value,
        endpoint=f"POST /api/controls/hvac/{zone}/setpoint",
        outcome="allowed",
        detail={"target_temperature": command.target_temperature},
    ))

    return SetpointResponse(
        status="command_sent",
        zone=zone,
        resource_id=resource.id,
        resource_type=resource.type.value,
        target_temperature=command.target_temperature,
        requested_by=subject.name,
        mqtt_topic=topic,
        timestamp=now,
    )
