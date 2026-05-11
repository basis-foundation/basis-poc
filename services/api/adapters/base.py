"""
BASIS — Adapter Base Class

Documents the interface that all protocol adapters must satisfy.
Stage 6: marker interface only. Full async lifecycle methods (start, stop,
send_command) will be formalised when a second adapter is introduced in Stage 10.

Design note: keep this minimal. An ABC with abstract methods that don't exist
yet in the only concrete implementation creates dead weight. The contract is
documented here so that future adapter authors know what to implement.
"""

from abc import ABC, abstractmethod


class AdapterBase(ABC):
    """
    Base class for BASIS protocol adapters.

    An adapter is responsible for two things:
      1. Receiving telemetry from a physical system and delivering it to
         the internal event model (TelemetryEvent).
      2. Accepting commands from the internal model (CommandEvent) and
         translating them into protocol-native messages for the device.

    Current concrete implementation: adapters/mqtt/ (Stage 6)
    Planned: adapters/bacnet/, adapters/modbus/ (Stage 10)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable adapter identifier used in logs and audit records.
        Example: "mqtt", "bacnet", "modbus-tcp"
        """
        ...
