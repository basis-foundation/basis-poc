"""
Basis Foundation — HVAC Control Endpoints
Stage 4: Operator/admin-only setpoint commands published to MQTT.
Stage 5: Command dispatch outcomes recorded to audit log.
Stage 7: Migrated from require_role() to require_action() + Subject.

Authorization:
  - viewer  → 403 Forbidden (denied by RoleBasedPolicy, recorded by require_action)
  - operator → allowed
  - admin   → allowed

Authorization now flows through:
  require_action(WRITE_HVAC_SETPOINT)
    → PolicyEngine.evaluate(subject, "write:hvac:setpoint")
    → RoleBasedPolicy checks _ACTION_ROLES table
    → PolicyResult(allowed=True/False)
    → AuditEvent recorded (authorization decision)
    → Subject returned to handler (or 403 raised)

Validation layers (unchanged):
  1. Pydantic field constraints  — type, ge/le bounds → 422 Unprocessable Entity
  2. Zone allow-list             — unknown zones → 404
  3. Simulator validates again   — belt-and-suspenders against broker replay attacks

Audit call sites in this module:
  - command_dispatch/allowed  — MQTT publish succeeded
  - command_dispatch/error    — MQTT publish failed (503 returned to caller)
Note: the authorization audit record (action=write:hvac:setpoint) is written by
require_action() in auth.py before this handler is reached. These two records
are complementary: one records the authorization decision, the other records
the delivery outcome.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Path
from pydantic import BaseModel, Field

from audit import audit_logger
from auth import require_action
from domain.events import AuditEvent
from domain.subject import Subject
from policy import actions
from adapters.mqtt.publisher import publish_command

router = APIRouter(prefix="/api/controls", tags=["controls"])

# Only zones that actually have a simulated device
VALID_ZONES = {"main"}

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
        "The simulator will receive the command and gradually drive "
        "`current_temperature` toward the new `target_temperature`."
    ),
)
async def set_hvac_setpoint(
    zone: Annotated[
        str,
        Path(description="Zone identifier — currently only 'main' is simulated"),
    ],
    command: SetpointCommand,
    subject: Subject = Depends(require_action(actions.WRITE_HVAC_SETPOINT)),
) -> SetpointResponse:
    # Zone validation — checked after authorization so an unauthorized caller
    # cannot enumerate valid zones by probing for 404 vs 403.
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown zone '{zone}'. Valid zones: {sorted(VALID_ZONES)}",
        )

    now         = datetime.now(timezone.utc).isoformat()
    topic       = f"basis/hvac/{zone}/command"
    resource_id = f"hvac:{zone}"

    mqtt_payload = {
        "target_temperature": command.target_temperature,
        "requested_by":       subject.name,
        "zone":               zone,
        "timestamp":          now,
    }

    try:
        await publish_command(topic, mqtt_payload)
    except RuntimeError as exc:
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action="command_dispatch",
            resource_id=resource_id,
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
        resource_id=resource_id,
        endpoint=f"POST /api/controls/hvac/{zone}/setpoint",
        outcome="allowed",
        detail={"target_temperature": command.target_temperature},
    ))

    return SetpointResponse(
        status="command_sent",
        zone=zone,
        target_temperature=command.target_temperature,
        requested_by=subject.name,
        mqtt_topic=topic,
        timestamp=now,
    )
