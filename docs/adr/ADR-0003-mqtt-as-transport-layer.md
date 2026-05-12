# ADR-0003 — MQTT as Transport Layer Only

**Status:** Accepted  
**Date:** 2025-05-01  

## Context

MQTT is the message transport between the OT simulator and the API. Telemetry flows from the simulator to the API via MQTT topics; commands flow from the API to the simulator via MQTT topics. In early stages of the project, MQTT payloads were parsed directly wherever they were consumed — the topic string and raw JSON dict were the de facto domain model for operational events.

This created a coupling problem. The MQTT topic structure (`basis/hvac/main/telemetry`) encoded resource identity implicitly: the resource type and zone were embedded in the topic path, not represented as typed fields. Any code that needed to know *what* an event was about had to parse the topic string. The internal representation of a telemetry event was indistinguishable from its wire format.

Similarly, the command payload sent to the MQTT broker was constructed inline in the controls router — a raw dict assembled from handler inputs — with no typed representation of what a command meant from a domain perspective.

The consequence was that the transport format was the domain model. Changing the MQTT topic structure would require changes throughout the codebase. Adding a second transport protocol (BACnet, Modbus, REST polling) would require parallel code paths that duplicated all the business logic.

## Decision

MQTT is treated as a transport layer only. The canonical representation of operational events is defined in `domain/events.py` as typed Pydantic models, independent of the transport that carries them.

`TelemetryEvent` represents an inbound telemetry observation with explicit fields for `resource_id`, `resource_type`, `source` (the MQTT topic), `timestamp`, and the original `payload` dict. It is constructed in the MQTT subscriber after JSON parse, using the `TOPIC_TO_RESOURCE` mapping to resolve the resource identity from the topic string. The WebSocket broadcaster continues to receive the original topic and payload dict — the wire format to the frontend is unchanged.

`CommandEvent` represents an outbound control command with explicit fields for `command_type`, `resource_id`, `resource_type`, `subject_id`, `subject_name`, `action`, and `payload`. It is constructed in the controls router before the MQTT publish, capturing the full command context in one typed object. The MQTT publisher continues to receive `command_event.payload` — the MQTT wire format to the simulator is unchanged.

The transport adapters (`adapters/mqtt/`) are responsible for the translation between wire format and domain model. Nothing outside `adapters/` interacts with raw MQTT topics or payloads.

## Consequences

**Accepted trade-offs:**
- The `TOPIC_TO_RESOURCE` mapping in `adapters/mqtt/topics.py` must be kept in sync with the static resource registry in `domain/resource.py`. This is a small, explicit coupling point that is easy to audit.
- `TelemetryEvent` and `CommandEvent` add construction overhead per message. For the current telemetry rates (sub-second intervals), this overhead is negligible.

**Benefits realized:**
- Adding a second transport protocol requires only a new adapter that translates its wire format into the existing `TelemetryEvent` / `CommandEvent` models. The policy layer, audit layer, and WebSocket delivery layer require no changes.
- The WebSocket wire format and MQTT payload format are stable contracts. Internal architecture can evolve — new fields on domain models, new normalization steps, new routing logic — without breaking external consumers.
- Audit events record the resource identity directly (`resource_id=hvac:main`) rather than requiring the audit reviewer to parse a topic string (`basis/hvac/main/telemetry`). The audit trail is independent of transport topology.
- The domain models serve as documentation. Reading `CommandEvent` tells you exactly what context is captured when a command is issued, without tracing through topic string conventions.

See also: [ADR-0005](ADR-0005-subject-resource-event-normalization.md), [ADR-0007](ADR-0007-wire-compatibility-during-refactors.md).
