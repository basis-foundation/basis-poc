"""
BASIS — Modbus Register Bank (In-Memory Simulation)
Stage 10: Lightweight in-memory simulation of a Modbus device's register state.

Register map
─────────────
Chiller Unit 1 (device:chiller-1)
  HR 40001  supply_temp_setpoint   Writable. Encoded °C × 10. Default: 180 (18.0 °C)
  IR 30001  supply_temp_actual     Read-only. Encoded °C × 10. Drifts toward setpoint.
  IR 30002  chiller_status         Read-only. 1 = running, 0 = stopped.

Pump Unit 1 (device:pump-1)
  HR 40101  speed_pct              Writable. Percentage 0–100. Default: 75
  IR 30101  flow_lpm               Read-only. Proportional to speed_pct × 6.
  IR 30102  pump_status            Read-only. 1 = running, 0 = stopped.

Integer encoding note
──────────────────────
Modbus holding/input registers are 16-bit unsigned integers. Temperatures are
stored as °C × 10 (fixed-point, one decimal place). Register 40001 = 185 means
18.5 °C. The adapter decodes to float before broadcasting telemetry payloads and
re-encodes when writing commands from the HTTP layer.

No real Modbus TCP socket is opened. This bank is the authoritative device state.
"""

import threading


class ModbusRegisterBank:
    """
    Thread-safe in-memory Modbus register simulation.

    Holding registers (HR) are read/write — operators update these via the
    command endpoint. Input registers (IR) are read-only from the outside —
    the simulation loop advances them on each tick() call.

    asyncio is single-threaded, so the threading.Lock is technically redundant
    for the current implementation. It is included because command writes and
    the simulation tick could theoretically be separated across threads in a
    future configuration.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Holding registers — writable by operators
        self._holding: dict[int, int] = {
            40001: 180,   # chiller-1: setpoint = 18.0 °C  (× 10)
            40101:  75,   # pump-1:    speed_pct = 75 %
        }

        # Input registers — read-only externally, updated by tick()
        self._input: dict[int, int] = {
            30001: 210,   # chiller-1: actual supply temp = 21.0 °C  (× 10)
            30002:   1,   # chiller-1: status = running
            30101: 450,   # pump-1:    flow = 450 L/min
            30102:   1,   # pump-1:    status = running
        }

    # ── Register access ───────────────────────────────────────────────────────

    def read_holding(self, address: int) -> int:
        with self._lock:
            return self._holding[address]

    def write_holding(self, address: int, value: int) -> None:
        with self._lock:
            if address not in self._holding:
                raise KeyError(f"No holding register at address {address}")
            self._holding[address] = value

    def read_input(self, address: int) -> int:
        with self._lock:
            return self._input[address]

    # ── Simulation tick ───────────────────────────────────────────────────────

    def tick(self) -> None:
        """
        Advance simulation one step.

        Chiller: actual supply temperature drifts toward setpoint at ≤ 0.5 °C/tick.
        Pump:    flow rate is proportional to speed_pct (100 % → 600 L/min).

        Called exclusively by the adapter background loop, never by command handlers.
        """
        with self._lock:
            # Chiller drift — stored as × 10, so 5 units = 0.5 °C
            setpoint = self._holding[40001]
            actual   = self._input[30001]
            diff     = setpoint - actual
            if diff != 0:
                step = min(abs(diff), 5)
                self._input[30001] = actual + (step if diff > 0 else -step)

            # Pump flow proportional to speed
            self._input[30101] = int(self._holding[40101] * 6.0)

    # ── Telemetry snapshots ───────────────────────────────────────────────────

    def snapshot_chiller(self) -> dict:
        """Return current chiller state as a telemetry payload dict."""
        with self._lock:
            return {
                "supply_temp_setpoint_c": self._holding[40001] / 10.0,
                "supply_temp_actual_c":   self._input[30001]   / 10.0,
                "status":                 "running" if self._input[30002] else "stopped",
                "adapter":                "modbus-tcp",
                "protocol":               "modbus-tcp",
            }

    def snapshot_pump(self) -> dict:
        """Return current pump state as a telemetry payload dict."""
        with self._lock:
            return {
                "speed_pct": self._holding[40101],
                "flow_lpm":  self._input[30101],
                "status":    "running" if self._input[30102] else "stopped",
                "adapter":   "modbus-tcp",
                "protocol":  "modbus-tcp",
            }
