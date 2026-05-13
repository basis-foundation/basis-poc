# ADR-0009 — Protocol-Agnostic Adapter Design

**Status:** Accepted  
**Date:** 2026-05-13  

## Context

BASIS was built from the outset to serve OT environments, where the diversity of field protocols is a given. A single building may use MQTT for HVAC telemetry, Modbus TCP for chiller plant control, BACnet/IP for floor-level zone management, and OPC-UA for historian integration. These protocols are not interchangeable — each has its own wire format, addressing model, and device semantics.

The question Stage 10 confronts is architectural: when a new OT protocol is integrated into BASIS, what must change?

The wrong answer is: everything. Adding BACnet/IP should not require modifying the JWT validation logic, the PolicyEngine, the audit store, or the WebSocket session model. Those components are correct and stable. Modifying them for each new protocol would create coupling that makes the platform progressively harder to extend and easier to break.

The right answer is: only the adapter. A new protocol adapter should be able to join BASIS by implementing a narrow interface and registering itself — without touching any security-path code.

Stage 10 validates this claim with a concrete implementation: a Modbus TCP adapter that runs alongside the existing MQTT adapter without modifying the identity model, policy engine, audit logger, or authorization flow.

## Decision

Introduce `AdapterBase` as the interface all OT protocol adapters must implement. `AdapterBase` defines two lifecycle methods — `start()` and `stop()` — and two class-level attributes: `adapter_id` and `protocol`. That is the complete interface.

Both the existing MQTT adapter and the new Modbus TCP adapter implement `AdapterBase`. Main application startup iterates the adapter registry and calls `start()` on each. Shutdown calls `stop()` in reverse order. No adapter-specific logic exists in `main.py`.

The security boundary is enforced at the router layer, not in the adapter. The Modbus command endpoints (`POST /api/controls/modbus/chiller-1/setpoint`, `POST /api/controls/modbus/pump-1/speed`) use `require_action(WRITE_MODBUS_SETPOINT)` — the same dependency as HVAC controls. Authorization is evaluated by the existing `PolicyEngine`. Audit events are written by the existing `audit_logger`. The Modbus adapter itself contains no authentication, authorization, or audit logic.

The telemetry path follows the same pattern. The Modbus adapter calls `broadcaster.broadcast(topic, payload)` — identical to the MQTT subscriber. WebSocket clients receive the same `{"type": "update", "topic": "...", "data": {...}}` wire format regardless of whether the data originated from MQTT or Modbus TCP. The frontend requires no changes.

Resources served by the Modbus adapter (`device:chiller-1`, `device:pump-1`) are registered in the existing static registry in `domain/resource.py` using the existing `DEVICE` ResourceType. They appear in `GET /api/resources` alongside MQTT-backed resources. The resource model has no knowledge of the underlying protocol.

## Consequences

**Accepted trade-offs:**

- The Modbus adapter is a simulation. No real Modbus TCP socket is opened. This is intentional — the goal of Stage 10 is architectural validation, not protocol completeness. A production-grade Modbus implementation would require the same `AdapterBase` interface with a different backend (e.g., `pymodbus`), leaving the security model unchanged.

- `AdapterBase` is deliberately minimal: two lifecycle methods and two attributes. More sophisticated interface contracts (read/write method signatures, subscription models, health check hooks) would be appropriate if BASIS were to become a general-purpose protocol gateway. For a PoC demonstrating protocol-agnosticism, a richer interface would be premature.

- The static resource registry (`domain/resource.py`) still requires a code change to add new resources. This constraint was accepted in ADR-0005 and is unchanged. A future stage may seed the registry from environment configuration at startup.

**Properties demonstrated:**

- A new OT protocol (Modbus TCP) was integrated without modifying `auth.py`, `policy/engine.py`, `policy/rbac.py`, `audit/store.py`, `ws_manager.py`, or any existing router.
- The single change to the policy layer — one new action constant and one new RBAC table entry — is the correct level of change: it records *what* the new protocol can do and *who* may do it. It does not introduce protocol-specific logic into the policy evaluation path.
- The audit trail for Modbus commands is structurally identical to the audit trail for HVAC commands. An operator reviewing the audit log sees consistent records regardless of which protocol generated them. Protocol identity (`adapter="modbus-tcp"`) is recorded in the detail dict, not in the action name or outcome field.
- Both adapters (`MqttAdapter`, `ModbusTcpAdapter`) are started, monitored, and stopped through the same `AdapterBase` interface in `main.py`. The number of registered adapters is not constrained by the application framework.
