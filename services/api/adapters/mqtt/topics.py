"""
BASIS — MQTT Topic Registry
Stage 7b: TOPIC_TO_RESOURCE mapping added for TelemetryEvent construction.

Single source of truth for all MQTT topic strings used by the API.

Naming convention: basis/{system}/{zone}/{message-type}

The simulator maintains its own copy of topic constants (it is a separate
container with no shared library). Both sides must agree on these strings.
Any change here must be reflected in services/simulator/simulator.py.
"""

# ── Telemetry topics (Simulator → Broker → API) ───────────────────────────────
TELEMETRY_HVAC      = "basis/hvac/main/telemetry"
TELEMETRY_CO2       = "basis/sensors/co2/telemetry"
TELEMETRY_OCCUPANCY = "basis/sensors/occupancy/telemetry"

# ── Command topics (API → Broker → Simulator) ─────────────────────────────────
# Use command_topic() to construct per-zone command topics.
CMD_HVAC_WILDCARD   = "basis/hvac/+/command"   # used by simulator subscriber

# ── Simulator metadata topics ─────────────────────────────────────────────────
SIMULATOR_STATUS    = "basis/simulator/status"
SIMULATOR_HEARTBEAT = "basis/simulator/heartbeat"

# ── Subscription wildcards ────────────────────────────────────────────────────
SUBSCRIBE_ALL = "basis/#"   # API subscribes to everything; filter in handler

# ── Known topics set — used to detect unexpected topics in the subscriber ─────
KNOWN_TOPICS = {
    TELEMETRY_HVAC,
    TELEMETRY_CO2,
    TELEMETRY_OCCUPANCY,
    SIMULATOR_STATUS,
    SIMULATOR_HEARTBEAT,
}


# ── Topic → Resource mapping (Stage 7b) ──────────────────────────────────────
# Maps each telemetry topic to its normalized resource ID.
# Used by the MQTT subscriber to populate TelemetryEvent.resource_id and
# TelemetryEvent.resource_type without parsing the topic string.
#
# Only telemetry topics are listed — command and simulator metadata topics
# are not resource-bearing in the context of TelemetryEvent construction.
TOPIC_TO_RESOURCE: dict[str, str] = {
    TELEMETRY_HVAC:      "hvac:main",
    TELEMETRY_CO2:       "sensor:co2",
    TELEMETRY_OCCUPANCY: "sensor:occupancy",
}


# ── Topic constructors ────────────────────────────────────────────────────────

def command_topic(resource_type: str, zone: str) -> str:
    """
    Build a command topic for a given resource type and zone.
    Example: command_topic("hvac", "main") → "basis/hvac/main/command"
    """
    return f"basis/{resource_type}/{zone}/command"


def telemetry_topic(resource_type: str, zone: str) -> str:
    """
    Build a telemetry topic for a given resource type and zone.
    Example: telemetry_topic("hvac", "main") → "basis/hvac/main/telemetry"
    """
    return f"basis/{resource_type}/{zone}/telemetry"
