"""
BASIS — Adapter Base Class
Stage 6:  Marker interface only.
Stage 10: Formalised with adapter_id, protocol, start(), and stop().
          Both MqttAdapter and ModbusTcpAdapter implement this interface.

The AdapterBase contract ensures that new OT protocols (Modbus TCP, BACnet/IP,
DNP3, OPC-UA, etc.) can be integrated into BASIS without modifying:
  - The identity model  (domain/subject.py, domain/session.py)
  - The policy engine   (policy/engine.py, policy/rbac.py)
  - The audit logger    (audit/store.py)
  - The authorization flow (auth.py, require_action())

Adapters are responsible for:
  1. Lifecycle  — starting and stopping their background I/O tasks
  2. Telemetry  — calling broadcaster.broadcast(topic, payload) to push data
  3. Protocol   — reading and writing via their specific OT wire protocol

Adapters are NOT responsible for:
  - Identity validation  (auth.py handles this for all protocols)
  - Authorization checks (PolicyEngine handles this for all protocols)
  - Audit recording      (routers record AuditEvents on the standard path)
  - WebSocket sessions   (ws_manager.py handles this for all protocols)

This separation is the architectural claim of Stage 10: security enforcement
is centralized and protocol-agnostic. A new protocol adapter inherits the full
BASIS security model without implementing any security logic itself.

Implementations
───────────────
  MqttAdapter      — MQTT 3.1.1  (adapters/mqtt/subscriber.py)
  ModbusTcpAdapter — Modbus TCP  (adapters/modbus/adapter.py)
"""

from abc import ABC, abstractmethod


class AdapterBase(ABC):
    """
    Abstract base class for all OT protocol adapters in BASIS.

    A compliant adapter:
      - Declares adapter_id and protocol as class-level string attributes
      - Implements start() to launch background I/O or simulation tasks
      - Implements stop() to cleanly cancel those tasks and release resources

    The adapter_id is used as the asyncio task name and in log lines.
    The protocol string appears in audit event detail dicts so operators
    can distinguish, e.g., Modbus reads from MQTT reads in the audit log.
    """

    adapter_id: str
    # Short stable identifier — e.g. "mqtt", "modbus-tcp".
    # Used in log messages and as the asyncio task name.

    protocol: str
    # Protocol descriptor — e.g. "mqtt", "modbus-tcp".
    # Appears verbatim in audit event detail dicts. Stable once shipped.

    @abstractmethod
    async def start(self) -> None:
        """
        Start the adapter's background tasks.

        Called once during application startup. Must return quickly —
        schedule asyncio tasks here, do not block or await long operations.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """
        Gracefully shut down the adapter.

        Cancel background tasks, flush pending state, close connections.
        Called during application shutdown in reverse registration order.
        """
        ...
