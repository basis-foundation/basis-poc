"""
BASIS — Resource Domain Model
Stage 8:  Introduces normalized OT resource concepts.
Stage 10: Modbus-backed device resources added (device:chiller-1, device:pump-1).
          No new ResourceType enum values were required — DEVICE covers generic
          OT devices regardless of the protocol adapter serving them. This is an
          intentional design proof: the resource model is protocol-agnostic.

Why Resource exists
────────────────────
Prior stages identified resources with ad hoc strings: f"hvac:{zone}" constructed
inline in the controls router. That string appeared in audit logs but carried no
type information, no zone context, and no validation — it was just a label.

Resource formalizes what a "thing that can be targeted by an action" means in an
OT control plane:
  - It has a canonical normalized identifier ("hvac:main")
  - It has a type (HVAC, SENSOR, ZONE, DEVICE, GATEWAY)
  - It belongs to a logical zone
  - It can be resolved from the registry by ID

This matters for the policy layer:
  Stage 7 answers "may subject S perform action A?"
  Stage 8 answers "may subject S perform action A on resource R?"
  Stage 9 will use zone membership to answer "may subject S perform action A
    on any resource in zone Z?"

The resource model is kept intentionally static in Stage 8. There is no database,
no discovery protocol, no CMDB integration. Known resources are defined here as
plain Python objects. Adding a new simulated device means adding one entry to
_REGISTRY. That is the correct level of complexity for a PoC.

ResourceType
────────────
  HVAC     — heating, ventilation, and air conditioning controllers
  SENSOR   — environmental sensors (CO₂, temperature, occupancy, humidity, ...)
  ZONE     — logical groupings of physical resources (floor, wing, building)
  DEVICE   — generic OT device not covered by a more specific type
  GATEWAY  — protocol bridge or edge gateway (BACnet, Modbus, OPC-UA)

ResourceIdentifier
──────────────────
Parses and constructs the normalized resource ID format used throughout BASIS:

  "{type}:{qualifier[:{subqualifier}...]}"

  "hvac:main"          → HVAC device named "main"
  "sensor:co2"         → CO₂ sensor
  "sensor:co2:lobby"   → CO₂ sensor in the lobby subzone
  "zone:main"          → The main logical zone
  "gateway:bacnet"     → A BACnet/IP gateway

ResourceIdentifier.build() is the preferred way to construct resource IDs —
it avoids f-string concatenation scattered across the codebase and ensures
the type prefix always matches the ResourceType enum value.

Static Registry
───────────────
_REGISTRY is the authoritative list of known resources in this deployment.
resolve_resource() and list_resources() are the public API for lookups.

Stage 9 will introduce a mutable runtime registry seeded from this static
definition, allowing zones and devices to be registered at startup from
configuration rather than source code.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ResourceType(str, Enum):
    """
    Classification of OT resources BASIS can authorize actions against.

    Using str as the base makes ResourceType JSON-serializable and printable
    as a plain string in audit logs and API responses.
    """
    HVAC    = "hvac"     # HVAC controller (setpoint, mode, fan speed)
    SENSOR  = "sensor"   # Environmental sensor (CO₂, temperature, occupancy)
    ZONE    = "zone"     # Logical zone grouping physical resources
    DEVICE  = "device"   # Generic OT device not covered by a specific type
    GATEWAY = "gateway"  # Protocol bridge (BACnet/IP, Modbus TCP, OPC-UA)


class Resource(BaseModel):
    """
    A named OT resource that can be targeted by subjects performing actions.

    The id field is the canonical normalized identifier — it is the string that
    appears in audit logs, MQTT topics (derived), and API responses.

    Format: "{type}:{name}" or "{type}:{subtype}:{qualifier}"

    Examples:
      Resource(id="hvac:main",        type=HVAC,   name="main",       zone="main")
      Resource(id="sensor:co2",       type=SENSOR, name="co2",        zone="main")
      Resource(id="sensor:occupancy", type=SENSOR, name="occupancy",  zone="main")
      Resource(id="zone:main",        type=ZONE,   name="main")

    Immutable — created once at module load from the static registry.
    """

    id:          str            # Canonical normalized identifier
    type:        ResourceType
    name:        str            # Short identifier component after the type prefix
    zone:        Optional[str] = None   # Logical zone this resource belongs to
    description: Optional[str] = None  # Human-readable description

    model_config = {"frozen": True}

    def __str__(self) -> str:
        return self.id


class ResourceIdentifier:
    """
    Parses and constructs normalized resource ID strings.

    This class exists to prevent f-string resource ID construction scattered
    across the codebase. All resource ID strings flow through either:
      ResourceIdentifier.build(type, *parts)  — construction
      ResourceIdentifier(raw)                 — parsing

    Parsing examples:
      ResourceIdentifier("hvac:main").type_str     → "hvac"
      ResourceIdentifier("hvac:main").qualifiers   → ["main"]
      ResourceIdentifier("sensor:co2").type_str    → "sensor"
      ResourceIdentifier("sensor:co2").qualifiers  → ["co2"]

    Building examples:
      ResourceIdentifier.build(ResourceType.HVAC, "main")          → "hvac:main"
      ResourceIdentifier.build(ResourceType.SENSOR, "co2")         → "sensor:co2"
      ResourceIdentifier.build(ResourceType.SENSOR, "co2", "lobby")→ "sensor:co2:lobby"
    """

    __slots__ = ("raw", "type_str", "qualifiers")

    def __init__(self, resource_id: str) -> None:
        parts          = resource_id.split(":")
        self.raw       = resource_id
        self.type_str  = parts[0] if parts else ""
        self.qualifiers = parts[1:] if len(parts) > 1 else []

    @staticmethod
    def build(resource_type: ResourceType, *parts: str) -> str:
        """
        Construct a normalized resource ID from a ResourceType and qualifier parts.

        ResourceIdentifier.build(ResourceType.HVAC, "main")           → "hvac:main"
        ResourceIdentifier.build(ResourceType.SENSOR, "co2")          → "sensor:co2"
        ResourceIdentifier.build(ResourceType.SENSOR, "co2", "lobby") → "sensor:co2:lobby"
        ResourceIdentifier.build(ResourceType.ZONE, "main")           → "zone:main"
        """
        return ":".join([resource_type.value] + list(parts))

    def __repr__(self) -> str:
        return f"ResourceIdentifier({self.raw!r})"


# ── Static Resource Registry ───────────────────────────────────────────────────
#
# The authoritative list of known OT resources in this BASIS deployment.
# All resources that can appear in authorization decisions or audit events
# must be registered here.
#
# Stage 8: static definition only. No database. No discovery protocol.
# Stage 9: this dict will seed a mutable runtime registry so that multi-zone
#          configurations can be loaded from environment config at startup.
#
# How to add a new resource:
#   1. Choose a normalized ID following the "{type}:{name}" convention
#   2. Add it to this dict
#   3. If it publishes MQTT telemetry, add the topic to adapters/mqtt/topics.py
#
_REGISTRY: dict[str, Resource] = {

    # ── HVAC resources ─────────────────────────────────────────────────────────
    # One HVAC controller per zone. Zone name matches the MQTT zone segment.
    ResourceIdentifier.build(ResourceType.HVAC, "main"): Resource(
        id=ResourceIdentifier.build(ResourceType.HVAC, "main"),
        type=ResourceType.HVAC,
        name="main",
        zone="main",
        description="Main zone HVAC controller — setpoint, mode, fan speed",
    ),

    # ── Sensor resources ───────────────────────────────────────────────────────
    ResourceIdentifier.build(ResourceType.SENSOR, "co2"): Resource(
        id=ResourceIdentifier.build(ResourceType.SENSOR, "co2"),
        type=ResourceType.SENSOR,
        name="co2",
        zone="main",
        description="CO₂ sensor — main zone air quality monitoring (ppm)",
    ),
    ResourceIdentifier.build(ResourceType.SENSOR, "occupancy"): Resource(
        id=ResourceIdentifier.build(ResourceType.SENSOR, "occupancy"),
        type=ResourceType.SENSOR,
        name="occupancy",
        zone="main",
        description="Occupancy sensor — main zone headcount detection",
    ),

    # ── Modbus-backed device resources (Stage 10) ─────────────────────────────
    # These resources are served by the Modbus TCP adapter (adapters/modbus/).
    # They use the existing DEVICE type — the resource model has no knowledge
    # of the underlying protocol. The same resolve_resource() and list_resources()
    # API exposes them alongside MQTT-backed resources at GET /api/resources.
    ResourceIdentifier.build(ResourceType.DEVICE, "chiller-1"): Resource(
        id=ResourceIdentifier.build(ResourceType.DEVICE, "chiller-1"),
        type=ResourceType.DEVICE,
        name="chiller-1",
        zone="plant",
        description=(
            "Primary chiller unit — Modbus TCP adapter. "
            "HR 40001: supply temp setpoint (°C × 10). "
            "IR 30001: actual supply temp. IR 30002: running status."
        ),
    ),
    ResourceIdentifier.build(ResourceType.DEVICE, "pump-1"): Resource(
        id=ResourceIdentifier.build(ResourceType.DEVICE, "pump-1"),
        type=ResourceType.DEVICE,
        name="pump-1",
        zone="plant",
        description=(
            "Primary circulation pump — Modbus TCP adapter. "
            "HR 40101: speed setpoint (%). "
            "IR 30101: flow rate (L/min). IR 30102: running status."
        ),
    ),

    # ── Zone resources ─────────────────────────────────────────────────────────
    # Zones group physical resources. Useful for zone-scoped policy grants (Stage 9).
    ResourceIdentifier.build(ResourceType.ZONE, "main"): Resource(
        id=ResourceIdentifier.build(ResourceType.ZONE, "main"),
        type=ResourceType.ZONE,
        name="main",
        zone=None,  # zones are not themselves within a zone
        description=(
            "Main building zone — contains the HVAC controller, "
            "CO₂ sensor, and occupancy sensor"
        ),
    ),
}


def resolve_resource(resource_id: str) -> Optional[Resource]:
    """
    Look up a Resource by its normalized ID.

    Returns the Resource if found, or None if the ID is not registered.
    None is the correct return for an unknown resource — callers decide
    whether to raise 404, fall back, or log a warning.

    Example:
        resource = resolve_resource("hvac:main")
        if resource is None:
            raise HTTPException(404, "Unknown resource")
        # resource.type.value → "hvac"
        # resource.zone       → "main"
    """
    return _REGISTRY.get(resource_id)


def list_resources(resource_type: Optional[ResourceType] = None) -> list[Resource]:
    """
    Return all known resources, optionally filtered by ResourceType.

    list_resources()                    → all registered resources
    list_resources(ResourceType.HVAC)   → only HVAC resources
    list_resources(ResourceType.SENSOR) → only sensor resources

    Result order reflects insertion order of _REGISTRY (Python 3.7+).
    """
    resources = list(_REGISTRY.values())
    if resource_type is not None:
        resources = [r for r in resources if r.type == resource_type]
    return resources
