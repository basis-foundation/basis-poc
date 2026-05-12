# ADR-0007 — Preserve Wire Compatibility During Internal Refactors

**Status:** Accepted  
**Date:** 2025-05-01  

## Context

Several stages of BASIS involved significant internal refactors that restructured the authorization model, domain representations, and event handling:

- **Stage 7** migrated from raw role checks (`require_role()`) to an action-based policy engine (`require_action()`). This touched the authorization layer, the audit layer, and all routers.
- **Stage 8** replaced hardcoded zone validation (`VALID_ZONES` set) with a typed resource registry. The `AuditEvent` model gained a `resource_type` field.
- **Stage 7b** introduced `TelemetryEvent` and `CommandEvent` as typed internal representations, replacing inline dict construction in the subscriber and controls router.

In each case, there were external contracts that consumers depended on:

- The **WebSocket wire format**: clients receive messages as `{type: "topic_string", data: {...payload}}`. The topic string and payload structure are what the frontend expects.
- The **MQTT payload format**: the simulator receives command payloads as `{target_temperature, requested_by, zone, timestamp}`. Changes to this format require a coordinated update to the simulator.
- The **REST API response shapes**: external consumers and tests depend on consistent field names and structures in HTTP responses.

A refactor that inadvertently changed these contracts would silently break external consumers in a way that might not be caught until runtime.

## Decision

Internal architecture changes must not alter external wire formats. The constraint is explicitly enforced at each refactor:

- The WebSocket broadcaster receives the same `(topic, payload)` arguments regardless of what internal processing has occurred. `TelemetryEvent` is constructed from the payload and used for internal logging; it is not sent to the WebSocket. The broadcaster call `await broadcaster.broadcast(topic, payload)` is unchanged.
- The MQTT publisher receives `command_event.payload` — which is the same dict that was previously assembled inline — unchanged. The `CommandEvent` wraps the payload in a typed object; it does not reformat or extend it.
- HTTP response models (`SetpointResponse`, `_resource_dict`, etc.) are defined explicitly and tested against expected shapes. New fields may be added but existing fields are not renamed or removed without a corresponding API version increment.

When a refactor is planned, the approach is: first establish the new internal representation; then verify that the translation to the external format is byte-for-byte equivalent to the previous implementation; then remove the old implementation.

This is not a formal contract testing regime. It is a discipline: changes to internal representations and changes to external contracts are separated into distinct, reviewable commits, and the distinction is documented in commit messages and PR descriptions.

## Consequences

**Accepted trade-offs:**
- Preserving backward-compatible wire formats constrains the pace at which internal domain models can diverge from the external representation. At some point, a version negotiation or migration path will be needed if the external contract genuinely needs to change.
- The `command_event.payload` forwarded to the MQTT publisher is the same dict that was previously assembled inline. This means `CommandEvent.payload` is not a richly typed field — it contains the MQTT-specific keys (`target_temperature`, `requested_by`, `zone`, `timestamp`) rather than domain-level fields. A future refactor may introduce explicit payload translation at the adapter boundary.

**Benefits realized:**
- Large internal refactors can be executed, reviewed, and merged without requiring simultaneous changes to the simulator, frontend, or any external consumer. The scope of change is bounded.
- The distinction between internal architecture (typed domain models) and external contracts (wire formats) is explicit. Contributors who change a domain model know to check the adapter translation; contributors who need to change a wire format know to look at the adapter, not the domain model.
- Operational stability during staged deployments. If a container running the new API version starts before the simulator is updated, commands still arrive in the format the simulator expects.

See also: [ADR-0003](ADR-0003-mqtt-as-transport-layer.md).
