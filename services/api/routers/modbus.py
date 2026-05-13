"""
BASIS — Modbus TCP Command Endpoints
Stage 10: Protocol-agnostic command routing for the Modbus TCP adapter.

  POST /api/controls/modbus/chiller-1/setpoint  — chiller supply temperature
  POST /api/controls/modbus/pump-1/speed        — pump speed percentage

These endpoints use the same security stack as all other BASIS command endpoints:

  require_action() → PolicyEngine → RoleBasedPolicy → AuditEvent (authorization)
  handler          → modbus_adapter.write_*()       → AuditEvent (command_dispatch)

This is the architectural proof of Stage 10. The Modbus command path is secured
by the existing authorization infrastructure without any changes to:
  - auth.py          (JWT validation, require_action, get_current_subject)
  - policy/engine.py (PolicyEngine evaluation)
  - policy/rbac.py   (role table — one new entry added for WRITE_MODBUS_SETPOINT)
  - audit/store.py   (audit persistence)

Audit pattern (matches routers/controls.py exactly)
─────────────────────────────────────────────────────
  1. require_action(WRITE_MODBUS_SETPOINT) records action=write:modbus:setpoint
     outcome=allowed (or denied — handler never runs on deny).
  2. Handler records action=command_dispatch outcome=allowed/error with
     adapter="modbus-tcp", protocol="modbus-tcp", and register details in detail.

Two events per successful command: one authorization record, one delivery record.
This matches the HVAC controls pattern and gives auditors a complete trail.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from adapters.modbus.adapter import RESOURCE_CHILLER, RESOURCE_PUMP, modbus_adapter
from audit import audit_logger
from auth import require_action
from domain.events import AuditEvent
from domain.subject import Subject
from policy import actions

log = logging.getLogger("basis.modbus.router")
router = APIRouter(prefix="/api/controls/modbus", tags=["modbus"])


# ── Request schemas ───────────────────────────────────────────────────────────

class ChillerSetpointRequest(BaseModel):
    temperature: float = Field(
        ...,
        ge=5.0,
        le=25.0,
        description="Supply temperature setpoint in °C (5.0–25.0)",
        examples=[16.0],
    )


class PumpSpeedRequest(BaseModel):
    speed_pct: int = Field(
        ...,
        ge=0,
        le=100,
        description="Pump speed as a percentage of rated capacity (0–100)",
        examples=[75],
    )


# ── Chiller setpoint ──────────────────────────────────────────────────────────

@router.post(
    "/chiller-1/setpoint",
    summary="Set chiller supply temperature setpoint",
    description=(
        "Writes a new supply temperature setpoint to Modbus holding register HR 40001.\n\n"
        "The value is encoded as integer °C × 10 before writing (e.g. 16.5 °C → 165).\n\n"
        "The Modbus adapter simulation will drift `supply_temp_actual_c` toward the "
        "new setpoint at ≤ 0.5 °C per telemetry tick (every 10s).\n\n"
        "Uses the same authorization gate as all BASIS command endpoints. "
        "The identity model, PolicyEngine, and audit logger are unchanged.\n\n"
        "**Required action:** `write:modbus:setpoint` (operator, admin)."
    ),
)
async def set_chiller_setpoint(
    body:    ChillerSetpointRequest,
    subject: Subject = Depends(require_action(actions.WRITE_MODBUS_SETPOINT)),
) -> dict:
    try:
        register_detail = modbus_adapter.write_chiller_setpoint(body.temperature)
    except Exception as exc:
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action="command_dispatch",
            resource_id=RESOURCE_CHILLER,
            resource_type="device",
            endpoint="POST /api/controls/modbus/chiller-1/setpoint",
            outcome="error",
            reason=str(exc),
            detail={"adapter": "modbus-tcp", "protocol": "modbus-tcp",
                    "temperature": body.temperature},
        ))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Modbus write failed: {exc}",
        )

    await audit_logger.record(AuditEvent(
        subject_id=subject.id,
        subject_name=subject.name,
        subject_type=subject.type.value,
        subject_roles=subject.roles,
        action="command_dispatch",
        resource_id=RESOURCE_CHILLER,
        resource_type="device",
        endpoint="POST /api/controls/modbus/chiller-1/setpoint",
        outcome="allowed",
        detail={
            "adapter":  "modbus-tcp",
            "protocol": "modbus-tcp",
            **register_detail,
        },
    ))

    return {
        "status":      "accepted",
        "resource_id": RESOURCE_CHILLER,
        "adapter":     "modbus-tcp",
        "protocol":    "modbus-tcp",
        **register_detail,
    }


# ── Pump speed ────────────────────────────────────────────────────────────────

@router.post(
    "/pump-1/speed",
    summary="Set pump speed percentage",
    description=(
        "Writes a new speed setpoint to Modbus holding register HR 40101.\n\n"
        "Flow rate (`flow_lpm`) will update proportionally on the next telemetry tick.\n\n"
        "Uses the same authorization gate as all BASIS command endpoints.\n\n"
        "**Required action:** `write:modbus:setpoint` (operator, admin)."
    ),
)
async def set_pump_speed(
    body:    PumpSpeedRequest,
    subject: Subject = Depends(require_action(actions.WRITE_MODBUS_SETPOINT)),
) -> dict:
    try:
        register_detail = modbus_adapter.write_pump_speed(body.speed_pct)
    except Exception as exc:
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action="command_dispatch",
            resource_id=RESOURCE_PUMP,
            resource_type="device",
            endpoint="POST /api/controls/modbus/pump-1/speed",
            outcome="error",
            reason=str(exc),
            detail={"adapter": "modbus-tcp", "protocol": "modbus-tcp",
                    "speed_pct": body.speed_pct},
        ))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Modbus write failed: {exc}",
        )

    await audit_logger.record(AuditEvent(
        subject_id=subject.id,
        subject_name=subject.name,
        subject_type=subject.type.value,
        subject_roles=subject.roles,
        action="command_dispatch",
        resource_id=RESOURCE_PUMP,
        resource_type="device",
        endpoint="POST /api/controls/modbus/pump-1/speed",
        outcome="allowed",
        detail={
            "adapter":  "modbus-tcp",
            "protocol": "modbus-tcp",
            **register_detail,
        },
    ))

    return {
        "status":      "accepted",
        "resource_id": RESOURCE_PUMP,
        "adapter":     "modbus-tcp",
        "protocol":    "modbus-tcp",
        **register_detail,
    }
