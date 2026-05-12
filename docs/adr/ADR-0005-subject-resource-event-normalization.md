# ADR-0005 — Subject, Resource, and Event Normalization

**Status:** Accepted  
**Date:** 2025-04-01  

## Context

In early stages of BASIS, the core domain concepts were represented as ad hoc primitives:

- A subject was a raw JWT payload dict. Role checks happened by inspecting `payload.get("realm_access", {}).get("roles", [])` inline, scattered across handlers.
- A resource was an implicit string — `f"hvac:{zone}"` assembled at the point of use, with no type information and no validation beyond a hardcoded `VALID_ZONES` set.
- A telemetry event was a JSON dict from the MQTT broker. Its identity came from the topic string, which had to be parsed by every consumer.
- A command was a raw dict assembled in the controls handler and passed directly to the MQTT publisher.

This representation worked at small scale but had structural problems:

- The same JWT parsing logic was duplicated wherever subject information was needed.
- `"hvac:main"` appearing in an audit record was a string — there was no way to know from that string alone what type of resource it was, or whether it was a valid resource, without re-parsing and re-validating.
- Adding a new subject type (a service account, a device identity) required changes throughout the authorization path.
- The telemetry and command flows had no typed representation — business logic was interleaved with wire format handling.

The common theme is that transport-level and protocol-level representations were being used as domain representations. The domain had no independent vocabulary.

## Decision

Three normalized domain concepts were introduced as typed Pydantic models in `domain/`:

**`Subject`** (`domain/subject.py`) — represents an authenticated identity with stable fields: `id` (JWT `sub`), `name` (preferred username), `type` (`SubjectType` enum: human, device, service, gateway, agent), `roles`, and optional `email`. The single translation boundary is `subject_from_jwt(payload: dict) -> Subject`. After this point, nothing in the authorization or audit path touches the raw JWT dict.

**`Resource`** (`domain/resource.py`) — represents a named OT resource with `id` (normalized `"{type}:{name}"`), `type` (`ResourceType` enum: hvac, sensor, zone, device, gateway), `name`, `zone`, and `description`. Resources are defined in a static registry (`_REGISTRY`). `resolve_resource(id)` and `list_resources(type)` are the public API. The `ResourceIdentifier` class handles normalized ID construction and parsing, eliminating f-string assembly at point of use.

**`AuditEvent` / `TelemetryEvent` / `CommandEvent`** (`domain/events.py`) — represent the canonical forms of the three event types in the system. `AuditEvent` carries typed subject and resource fields rather than raw strings. `TelemetryEvent` carries a resolved `resource_id` and `resource_type` derived from the MQTT topic, not embedded in it. `CommandEvent` captures the full command context — subject, resource, action, payload — as a typed object rather than a collection of separately managed variables.

The `domain/` package has no imports from any other BASIS package. It is the base of the import graph. Everything else may import from `domain/`; `domain/` imports only from the standard library and Pydantic.

## Consequences

**Accepted trade-offs:**
- The static resource registry (`_REGISTRY` in `domain/resource.py`) requires a code change to add a new resource. This is intentional for the current stage — there is no discovery protocol, no CMDB integration, and no configuration-driven registration. A future stage will seed the registry from environment configuration at startup.
- Pydantic models add serialization overhead relative to raw dicts. For the current request volumes, this overhead is not measurable.

**Benefits realized:**
- Every authorization decision, audit record, and command event carries type-safe domain representations. There is no ambiguity about what `resource_id="hvac:main"` means — `resource_type="hvac"` is stored alongside it.
- Adding a new subject type requires adding a `SubjectType` enum variant and one `Policy` implementation. The authorization path, audit path, and all existing handlers are unchanged.
- The audit trail is self-describing. An audit event contains enough information to reconstruct the context of the decision without reference to the originating JWT, MQTT topic, or request payload.
- Protocol adapters have a clear job: translate wire formats into domain models at the boundary. Everything inside the boundary works with domain models.

See also: [ADR-0003](ADR-0003-mqtt-as-transport-layer.md), [ADR-0004](ADR-0004-action-based-authorization.md).
