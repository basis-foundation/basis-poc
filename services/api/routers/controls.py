"""
Basis Foundation — HVAC Control Endpoints
Stage 4: Operator/admin-only setpoint commands published to MQTT.

Authorization:
  - viewer  → 403 Forbidden
  - operator → allowed
  - admin   → allowed

Validation (three layers):
  1. Pydantic field constraints  — type, ge/le bounds → 422 Unprocessable Entity
  2. Zone allow-list             — unknown zones → 404
  3. Simulator validates again   — belt-and-suspenders against broker replay attacks
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Path
from pydantic import BaseModel, Field

from auth import require_role, get_roles
from mqtt_publisher import publish_command

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
        "**Required role:** `operator` or `admin`.\n\n"
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
    user: dict = Depends(require_role("operator", "admin")),
) -> SetpointResponse:
    # Zone validation
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown zone '{zone}'. Valid zones: {sorted(VALID_ZONES)}",
        )

    username = user.get("preferred_username", "unknown")
    now      = datetime.now(timezone.utc).isoformat()
    topic    = f"basis/hvac/{zone}/command"

    mqtt_payload = {
        "target_temperature": command.target_temperature,
        "requested_by":       username,
        "zone":               zone,
        "timestamp":          now,
    }

    try:
        await publish_command(topic, mqtt_payload)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Command could not be delivered: {exc}",
        )

    return SetpointResponse(
        status="command_sent",
        zone=zone,
        target_temperature=command.target_temperature,
        requested_by=username,
        mqtt_topic=topic,
        timestamp=now,
    )
