"""
BASIS — Modbus TCP Adapter
Stage 10: Protocol-agnostic adapter proof of concept.

This adapter demonstrates that a new OT protocol (Modbus TCP) integrates into
BASIS without modifying:
  - domain/subject.py    identity model
  - policy/engine.py     authorization
  - audit/store.py       audit logging
  - auth.py              JWT validation and require_action()
  - ws_manager.py        telemetry session management

Integration pattern
────────────────────
  Telemetry path (adapter → broadcaster → all WS clients):
    _telemetry_loop() ticks the register bank and calls
    broadcaster.broadcast(topic, payload) — identical to the MQTT subscriber.
    Clients receive {"type": "update", "topic": "...", "data": {...}} unchanged.

  Command path (HTTP router → adapter):
    POST /api/controls/modbus/chiller-1/setpoint
      → require_action(WRITE_MODBUS_SETPOINT)    ← same PolicyEngine
      → AuditEvent recorded by router            ← same audit logger
      → modbus_adapter.write_chiller_setpoint()  ← adapter-specific write

  No security logic lives in this file. Authorization is the router's job.

Telemetry topics
────────────────
  basis/modbus/chiller-1/telemetry
  basis/modbus/pump-1/telemetry

  These are synthetic routing keys, not real MQTT topics. They follow the
  same naming convention so the broadcaster snapshot dict stays consistent.
"""

import asyncio
import logging
from datetime import datetime, timezone

from adapters.base import AdapterBase
from adapters.modbus.registers import ModbusRegisterBank
from domain.events import TelemetryEvent
from ws_manager import broadcaster

log = logging.getLogger("basis.adapter.modbus")

# Synthetic topic keys — used as keys in the broadcaster's snapshot dict.
# Convention matches existing MQTT topics for consistency.
TOPIC_CHILLER = "basis/modbus/chiller-1/telemetry"
TOPIC_PUMP    = "basis/modbus/pump-1/telemetry"

# Normalized resource IDs — must match entries in domain/resource.py _REGISTRY
RESOURCE_CHILLER = "device:chiller-1"
RESOURCE_PUMP    = "device:pump-1"

TELEMETRY_INTERVAL_SECONDS = 10  # matches simulator heartbeat


class ModbusTcpAdapter(AdapterBase):
    """
    Simulated Modbus TCP adapter for BASIS.

    Implements AdapterBase. Manages an in-memory register bank and a background
    telemetry loop. The modbus command router calls write_chiller_setpoint() and
    write_pump_speed() directly on the module-level singleton instance.

    Architectural proof:
      start() / stop() follow the same lifecycle as MqttAdapter.
      broadcaster.broadcast() is called identically to the MQTT subscriber.
      TelemetryEvent is constructed identically to the MQTT subscriber.
      No authentication, authorization, or audit logic exists in this class.
    """

    adapter_id = "modbus-tcp"
    protocol   = "modbus-tcp"

    def __init__(self) -> None:
        self._registers = ModbusRegisterBank()
        self._task: asyncio.Task | None = None

    # ── AdapterBase lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background telemetry emission loop."""
        self._task = asyncio.create_task(
            self._telemetry_loop(),
            name=f"adapter-{self.adapter_id}",
        )
        log.info(
            "ModbusTcpAdapter started — emitting telemetry every %ds",
            TELEMETRY_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        """Cancel the telemetry loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("ModbusTcpAdapter stopped")

    # ── Telemetry loop ────────────────────────────────────────────────────────

    async def _telemetry_loop(self) -> None:
        """
        Tick simulation and broadcast telemetry on a fixed interval.
        Emits an initial snapshot immediately so WS clients see Modbus data
        on first connect before the first tick completes.
        """
        await self._emit_all()          # immediate snapshot

        while True:
            await asyncio.sleep(TELEMETRY_INTERVAL_SECONDS)
            self._registers.tick()
            await self._emit_all()

    async def _emit_all(self) -> None:
        await self._emit(TOPIC_CHILLER, RESOURCE_CHILLER, self._registers.snapshot_chiller())
        await self._emit(TOPIC_PUMP,    RESOURCE_PUMP,    self._registers.snapshot_pump())

    async def _emit(self, topic: str, resource_id: str, payload: dict) -> None:
        """
        Construct a TelemetryEvent (internal model) and broadcast to WS clients.
        Structurally identical to adapters/mqtt/subscriber.py _handle_message().
        """
        resource_type = resource_id.split(":")[0]

        # Internal normalized event — same pattern as MQTT adapter (Stage 7b)
        _event = TelemetryEvent(
            resource_id=resource_id,
            resource_type=resource_type,
            source=topic,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
        )

        log.debug(
            "modbus telemetry — resource=%s  payload_keys=%s",
            resource_id,
            [k for k in payload if k not in ("adapter", "protocol")],
        )

        # Broadcast to WebSocket clients — wire format unchanged from Stage 3
        await broadcaster.broadcast(topic, payload)

    # ── Command interface ─────────────────────────────────────────────────────

    def write_chiller_setpoint(self, temperature_c: float) -> dict:
        """
        Write a new supply temperature setpoint to holding register HR 40001.

        Called by the modbus router after authorization is confirmed by
        require_action(). Returns register details for the audit event detail.

        Encoding: setpoint stored as integer °C × 10. 18.5 °C → register 185.
        """
        register = 40001
        encoded  = round(temperature_c * 10)
        self._registers.write_holding(register, encoded)
        log.info(
            "chiller setpoint — HR %d = %d  (%.1f °C)",
            register, encoded, temperature_c,
        )
        return {
            "register_type":    "holding",
            "register_address": register,
            "encoded_value":    encoded,
            "decoded_value":    temperature_c,
            "unit":             "°C",
        }

    def write_pump_speed(self, speed_pct: int) -> dict:
        """
        Write a new speed setpoint to holding register HR 40101.

        Called by the modbus router after authorization is confirmed by
        require_action(). Returns register details for the audit event detail.
        """
        register = 40101
        self._registers.write_holding(register, speed_pct)
        log.info(
            "pump speed — HR %d = %d %%",
            register, speed_pct,
        )
        return {
            "register_type":    "holding",
            "register_address": register,
            "encoded_value":    speed_pct,
            "decoded_value":    speed_pct,
            "unit":             "%",
        }

    def read_state(self) -> dict:
        """Return full register state — for health checks and debugging."""
        return {
            "chiller_1": self._registers.snapshot_chiller(),
            "pump_1":    self._registers.snapshot_pump(),
        }


# Module-level singleton — imported by routers/modbus.py and main.py
modbus_adapter = ModbusTcpAdapter()
