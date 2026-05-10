# BASIS Platform Architecture

**Document status:** Draft — Stage 4 baseline  
**Scope:** Architectural refinement plan for evolving BASIS from an HVAC identity demo into a generalized open-source OT identity and authorization control plane.

This document does not describe the current Stage 4 implementation. It describes the target internal architecture and a concrete migration path to reach it — without rewrites, without microservices, without cloud dependencies.

---

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [Core Domain Abstractions](#core-domain-abstractions)
- [Proposed Project Structure](#proposed-project-structure)
- [Module Architecture](#module-architecture)
- [Data Models](#data-models)
- [Policy Engine Design](#policy-engine-design)
- [Normalized Telemetry Schema](#normalized-telemetry-schema)
- [Normalized Command Schema](#normalized-command-schema)
- [Audit Architecture](#audit-architecture)
- [Future Identity Types](#future-identity-types)
- [Incremental Migration Plan](#incremental-migration-plan)
- [Naming Improvements](#naming-improvements)
- [What Not To Build Yet](#what-not-to-build-yet)

---

## Design Philosophy

BASIS solves a specific, underserved problem: OT systems have historically had no meaningful identity layer. Authentication is absent or credential-based, authorization is all-or-nothing, and auditability is an afterthought. The goal is to introduce the standard IAM patterns that IT systems take for granted — without requiring operators to adopt cloud platforms, containerization expertise, or distributed systems knowledge.

The architecture principles that follow from this:

**Identity-first, protocol-agnostic.** The value BASIS delivers is authorization policy enforcement and audit trail. The transport protocol (MQTT, BACnet, Modbus, OPC-UA) is an adapter concern. The identity model and policy model should be completely independent of how the physical device communicates.

**Local-first and air-gap compatible.** Many OT environments cannot have cloud dependencies on the control path. Every component must run in a single Docker Compose stack with no external network requirements. This is a constraint that shapes every architectural decision.

**Progressive extensibility over upfront generalization.** Introduce abstractions when the second use case requires them. The current architecture supports one resource type (HVAC), one protocol (MQTT), and one identity type (human users). The refactoring proposed here introduces the structural slots for future types without requiring them to be filled.

**Auditability as infrastructure.** Every authorization decision — allowed or denied — and every command issued should be recorded with enough context to reconstruct what happened, who caused it, and why it was permitted. This is not a feature for Stage 5; it is a foundational design constraint from here forward.

**One process, clean internal modules.** The API is a monolith and should stay that way until there is a demonstrated operational reason to split it. The goal is clean internal module boundaries that could become service boundaries in the future — not premature separation.

---

## Core Domain Abstractions

These six abstractions form the vocabulary of the platform. Everything else is either an implementation of one of these concepts or a concern that sits between them.

### Subject

Any identity that can take an action. In Stage 4, all subjects are human users authenticated via Keycloak. The abstraction must accommodate future non-human identities without requiring changes to the policy engine or audit logger.

A Subject carries: a unique identifier, a type (human, device, service, gateway, agent), a display name, a list of roles or capabilities, and an open attributes map for type-specific metadata.

Critically, `Subject` is an internal domain model resolved from whatever authentication mechanism was used. The JWT-to-Subject translation is a concern of the `auth/` module. The policy engine never touches a JWT directly.

### Resource

Any OT entity that can be acted upon. In Stage 4, the only resource is the HVAC unit in zone "main." A Resource carries: a unique identifier (e.g., `hvac:main`), a type, a Zone association, the protocol adapter that owns it, and extensible metadata.

The resource identifier format `{type}:{zone}` is intentionally compact and human-readable. For multi-building deployments, this extends naturally to `{type}:{building}:{floor}:{zone}`.

### Action

A discrete operation that can be performed on a Resource. The action set is intentionally small and maps directly to authorization policy decisions. Fine-grained operations (e.g., "set HVAC to cooling mode" vs "set HVAC setpoint") are captured as `Action.COMMAND` with parameters — they are not separate action types at the authorization layer.

The current implicit actions in Stage 4 (read telemetry, send setpoint command) map directly to `READ` and `COMMAND`.

### Policy

A rule that governs whether a Subject may perform an Action on a Resource. In Stage 4, the implicit policy is role-based: operator and admin may COMMAND, all roles may READ. The policy abstraction separates the *enforcement point* (FastAPI dependency) from the *evaluation logic* (the policy engine), allowing the evaluation logic to be replaced or extended without touching route handlers.

### Zone

A physical or logical grouping of Resources. In Stage 4, there is one zone ("main"). Zones carry building and floor metadata, enabling hierarchical access control later (e.g., "operator on floor 3 may only command resources in zone floor3:*").

### Adapter

A translation layer between a physical protocol and the BASIS internal event model. In Stage 4, MQTT is the only transport and it is used for both telemetry ingestion and command dispatch. The Adapter abstraction makes this explicit: an adapter subscribes to protocol-native events, normalizes them into `TelemetryEvent` objects, and accepts `CommandEvent` objects which it translates back into protocol-native messages.

---

## Proposed Project Structure

This structure represents the target state. The migration plan below describes how to reach it incrementally. Each directory corresponds to a distinct concern; nothing in this layout requires more than one OS process.

```
basis-poc/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── docs/
│   ├── platform-architecture.md    ← this document
│   └── screenshots/
│
├── infra/
│   ├── keycloak/
│   │   └── realm-export.json
│   └── mosquitto/
│       └── mosquitto.conf
│
└── services/
    ├── api/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   ├── main.py                  # app factory, lifespan, health endpoint
    │   ├── config.py                # centralized Settings via pydantic-settings
    │   │
    │   ├── domain/                  # core abstractions — no I/O, no FastAPI
    │   │   ├── __init__.py
    │   │   ├── subject.py           # Subject, SubjectType
    │   │   ├── resource.py          # Resource, ResourceType, Zone
    │   │   ├── action.py            # ActionType enum
    │   │   └── events.py            # TelemetryEvent, CommandEvent, AuditEvent
    │   │
    │   ├── auth/                    # identity verification (was: auth.py)
    │   │   ├── __init__.py
    │   │   ├── jwks.py              # JWKS fetch, cache, key rotation
    │   │   ├── tokens.py            # JWT decode and claim validation
    │   │   ├── subjects.py          # token payload → Subject resolution
    │   │   └── dependencies.py      # FastAPI Depends() factories
    │   │
    │   ├── policy/                  # authorization evaluation
    │   │   ├── __init__.py
    │   │   ├── engine.py            # PolicyEngine — evaluate(subject, action, resource)
    │   │   └── rbac.py              # RoleBasedPolicy — current viewer/operator/admin rules
    │   │
    │   ├── adapters/                # protocol bridges
    │   │   ├── __init__.py
    │   │   ├── base.py              # AdapterBase ABC
    │   │   └── mqtt/                # was: mqtt_client.py + mqtt_publisher.py
    │   │       ├── __init__.py
    │   │       ├── subscriber.py    # aiomqtt listener → normalizer → broadcaster
    │   │       ├── publisher.py     # CommandEvent → MQTT publish
    │   │       └── topics.py        # topic constants, topic→resource_id mapping
    │   │
    │   ├── telemetry/               # was: ws_manager.py
    │   │   ├── __init__.py
    │   │   ├── broadcaster.py       # WebSocket connection manager, fan-out
    │   │   └── normalizer.py        # raw MQTT payload → TelemetryEvent
    │   │
    │   ├── commands/                # command dispatch abstraction
    │   │   ├── __init__.py
    │   │   └── dispatcher.py        # CommandEvent → adapter routing
    │   │
    │   ├── audit/                   # audit logging (stub now, SQLite in Stage 5)
    │   │   ├── __init__.py
    │   │   ├── logger.py            # AuditLogger — write AuditEvent
    │   │   └── store.py             # persistence (stdout stub → SQLite)
    │   │
    │   └── routers/
    │       ├── identity.py          # was: protected.py (/api/me, role probes)
    │       ├── telemetry.py         # unchanged — /ws/telemetry WebSocket
    │       ├── commands.py          # was: controls.py (generalized path)
    │       └── audit.py             # stub — /api/audit (Stage 5)
    │
    ├── frontend/                    # React + Vite (unchanged structure)
    │   └── src/
    │       └── ...
    │
    └── simulator/
        └── simulator.py             # unchanged until Stage 8 multi-zone
```

---

## Module Architecture

### `domain/` — Core Abstractions

This package contains only Pydantic models and enums. No I/O, no FastAPI imports, no database calls. It is the lingua franca of the platform — every other module imports from here, nothing here imports from other modules. This constraint makes domain models testable in complete isolation and makes the abstraction boundaries explicit.

If BASIS ever splits into separate services, this package is the first candidate for extraction into a shared library.

### `auth/` — Identity Verification

Splits the current `auth.py` monolith into focused modules:

`jwks.py` owns the JWKS cache (the `_fetch_jwks` function and `_jwks` dict). `tokens.py` owns JWT decode and signature verification. `subjects.py` resolves a validated token payload into a `Subject` domain object. `dependencies.py` exposes the FastAPI `Depends()` factories (`get_current_subject`, `require_action`).

The key change from Stage 4 is that `get_current_user` (which returns a raw dict) becomes `get_current_subject` (which returns a typed `Subject`). Route handlers that currently inspect `user.get("preferred_username")` will instead use `subject.name`. This is a clean, mechanical migration.

`require_role("operator", "admin")` becomes `require_action(ActionType.COMMAND)` — the route declares what it needs, not which roles grant it. The policy engine decides whether the subject's roles satisfy that requirement.

### `policy/` — Authorization Evaluation

The policy engine separates the *where* (FastAPI dependency enforcement point) from the *what* (the actual decision logic). This separation has immediate value: policy rules can be unit-tested without spinning up a FastAPI app, and the rule set can be extended without touching route handlers.

`engine.py` defines `PolicyEngine` with a registered list of policies. Evaluation iterates policies in priority order and returns the first definitive decision. An unmatched evaluation returns a default-deny decision.

`rbac.py` implements `RoleBasedPolicy` — a direct translation of the current implicit role logic. This policy will produce identical authorization outcomes to the current `require_role()` implementation. It is registered as the first (and currently only) policy in the engine.

This design leaves a clean slot for future policy types: attribute-based policies (e.g., "operator may only command HVAC in their assigned building"), time-based policies (e.g., "setpoint changes require confirmation outside business hours"), or OPA-evaluated policies for complex rule sets.

### `adapters/` — Protocol Bridges

`base.py` defines `AdapterBase`, an abstract class with `start()`, `stop()`, and `send_command(command: CommandEvent)` methods. An adapter is responsible for translating between protocol-native wire formats and the BASIS internal event model.

The MQTT adapter refactors the current `mqtt_client.py` and `mqtt_publisher.py` into a single coherent module:

- `subscriber.py` runs the aiomqtt listener loop (currently in `mqtt_client.py`), but instead of forwarding raw JSON directly to the broadcaster, it passes through `normalizer.py` first.
- `publisher.py` accepts a `CommandEvent` and translates it back to a protocol-specific MQTT payload (currently in `mqtt_publisher.py`).
- `topics.py` centralizes topic string constants and the mapping from MQTT topic patterns to `resource_id` values.

When a BACnet adapter is added, it implements the same `AdapterBase` interface. Route handlers and the policy engine are entirely unaware of the transport.

### `telemetry/` — Ingestion and Fan-out

`broadcaster.py` is the current `ws_manager.py`, moved and renamed. Functionally unchanged.

`normalizer.py` is new. It takes a raw MQTT payload dict and the source topic, and returns a `TelemetryEvent`. This is where HVAC-specific field names like `current_temperature` are preserved in the payload but wrapped in a consistent envelope. The WebSocket broadcast message format shifts from raw JSON to a normalized envelope, which the frontend already handles (it receives `{type, topic, data}` — the `data` field just gains consistent metadata).

### `commands/` — Command Dispatch

`dispatcher.py` accepts a `CommandEvent` and routes it to the appropriate adapter based on `command.adapter`. In Stage 4 there is one adapter, so this is a simple direct call. The dispatcher is where future command acknowledgement tracking, delivery confirmation, and dead-letter handling would live.

### `audit/` — Audit Logging

Introduced now as a structural commitment, not as a fully implemented feature. `logger.py` defines `AuditLogger` with a single `record(event: AuditEvent)` method. `store.py` provides two implementations: `StdoutAuditStore` (logs to the uvicorn logger — the current behavior, just made explicit) and `SqliteAuditStore` (Stage 5 implementation, backed by `aiosqlite`).

The logger is called at two points: inside `dependencies.py` after every authorization decision, and inside `routers/commands.py` after every command dispatch (successful or failed). These two call sites cover the complete audit surface for the current system.

### `routers/` — HTTP and WebSocket Endpoints

`identity.py` replaces `protected.py`. The `/api/me` endpoint is unchanged. The `/api/viewer`, `/api/operator`, `/api/admin` probe endpoints are retained for the demo but are candidated for removal or replacement with a `/api/access-check` endpoint in Stage 7.

`commands.py` replaces `controls.py`. The path changes from `/api/controls/hvac/{zone}/setpoint` to `/api/commands/hvac/{zone}/setpoint`. This preserves HVAC specificity where it belongs (the resource type is part of the path) while removing "controls" in favor of "commands" as the canonical verb.

`audit.py` is a stub that returns 501 Not Implemented until Stage 5.

---

## Data Models

These are the canonical Pydantic models for the BASIS internal domain. Models in `domain/` have no FastAPI or database dependencies.

### Subject

```python
# domain/subject.py
from enum import Enum
from pydantic import BaseModel

class SubjectType(str, Enum):
    HUMAN   = "human"
    DEVICE  = "device"
    SERVICE = "service"
    GATEWAY = "gateway"
    AGENT   = "agent"

class Subject(BaseModel):
    id:         str              # JWT sub claim, device serial, or service identifier
    type:       SubjectType
    name:       str              # preferred_username, device name, service name
    roles:      list[str]        # realm roles for humans; capability tags for devices
    attributes: dict = {}        # issuer, email, device_model, service_version, etc.
```

### Resource and Zone

```python
# domain/resource.py
from enum import Enum
from pydantic import BaseModel

class ResourceType(str, Enum):
    HVAC             = "hvac"
    CO2_SENSOR       = "co2_sensor"
    OCCUPANCY_SENSOR = "occupancy_sensor"
    # Future:
    # ACCESS_CONTROL = "access_control"
    # LIGHTING       = "lighting"
    # ENERGY_METER   = "energy_meter"
    # BACNET_OBJECT  = "bacnet_object"
    # MODBUS_REGISTER = "modbus_register"

class Zone(BaseModel):
    id:       str
    name:     str
    building: str | None = None
    floor:    str | None = None

class Resource(BaseModel):
    id:       str           # "{type}:{zone_id}", e.g., "hvac:main"
    type:     ResourceType
    zone:     Zone
    protocol: str           # "mqtt", "bacnet", "modbus", "opcua"
    adapter:  str           # adapter instance name that owns this resource
    metadata: dict = {}     # resource-specific — capacity, units, firmware version, etc.
```

### ActionType

```python
# domain/action.py
from enum import Enum

class ActionType(str, Enum):
    READ        = "read"        # observe telemetry, query resource state
    SUBSCRIBE   = "subscribe"   # maintain a live telemetry subscription
    COMMAND     = "command"     # send a control command (setpoint, on/off, etc.)
    CONFIGURE   = "configure"   # change resource configuration (schedules, limits)
    ACKNOWLEDGE = "acknowledge" # acknowledge an alarm or alert
```

---

## Policy Engine Design

The policy engine is a chain-of-responsibility evaluator. Policies are registered in priority order. The engine iterates and returns the first definitive decision. If no policy matches, it returns default-deny.

```python
# policy/engine.py
from dataclasses import dataclass
from domain.subject import Subject
from domain.action import ActionType

@dataclass
class PolicyDecision:
    allowed:     bool
    reason:      str
    policy_name: str

class PolicyEngine:
    def __init__(self):
        self._policies: list = []

    def register(self, policy) -> None:
        self._policies.append(policy)

    def evaluate(
        self,
        subject:     Subject,
        action:      ActionType,
        resource_id: str,
    ) -> PolicyDecision:
        for policy in self._policies:
            decision = policy.evaluate(subject, action, resource_id)
            if decision is not None:
                return decision
        return PolicyDecision(
            allowed=False,
            reason="No policy matched — default deny",
            policy_name="default-deny",
        )
```

```python
# policy/rbac.py
# Direct translation of current Stage 4 require_role() behavior.
# Produces identical authorization outcomes — this is not a behavior change.

from domain.subject import Subject
from domain.action import ActionType
from policy.engine import PolicyDecision

_ROLE_PERMISSIONS: dict[str, set[ActionType]] = {
    "viewer":   {ActionType.READ, ActionType.SUBSCRIBE},
    "operator": {ActionType.READ, ActionType.SUBSCRIBE, ActionType.COMMAND},
    "admin":    {ActionType.READ, ActionType.SUBSCRIBE, ActionType.COMMAND,
                 ActionType.CONFIGURE, ActionType.ACKNOWLEDGE},
}

class RoleBasedPolicy:
    name = "rbac-v1"

    def evaluate(
        self,
        subject:     Subject,
        action:      ActionType,
        resource_id: str,
    ) -> PolicyDecision | None:
        # Check if any of the subject's roles grant the requested action
        for role in subject.roles:
            if action in _ROLE_PERMISSIONS.get(role, set()):
                return PolicyDecision(
                    allowed=True,
                    reason=f"Role '{role}' permits {action.value}",
                    policy_name=self.name,
                )

        # At least one known role was present but none permitted this action
        known_roles = set(subject.roles) & set(_ROLE_PERMISSIONS.keys())
        if known_roles:
            return PolicyDecision(
                allowed=False,
                reason=f"Roles {sorted(known_roles)} do not permit {action.value}",
                policy_name=self.name,
            )

        # No known roles — pass to the next policy in the chain
        return None
```

### FastAPI dependency integration

```python
# auth/dependencies.py
from fastapi import Depends, HTTPException, status
from policy.engine import PolicyEngine
from domain.action import ActionType
from domain.subject import Subject

# Module-level engine instance, policies registered at startup
policy_engine = PolicyEngine()

def require_action(action: ActionType):
    """
    FastAPI dependency factory. Replaces require_role().
    Usage: user: Subject = Depends(require_action(ActionType.COMMAND))
    """
    async def _enforce(subject: Subject = Depends(get_current_subject)) -> Subject:
        decision = policy_engine.evaluate(subject, action, resource_id="*")
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=decision.reason,
            )
        return subject
    return _enforce
```

### Path to OPA

The `PolicyEngine` design is intentionally compatible with an OPA (Open Policy Agent) backend. When rule complexity grows beyond what inline Python manages cleanly, `rbac.py` can be replaced with an `OpaPolicy` class that makes an HTTP call to a local OPA instance. The engine, dependencies, and route handlers are unchanged. This is a realistic Stage 9+ concern.

---

## Normalized Telemetry Schema

```python
# domain/events.py (TelemetryEvent)
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class TelemetryEvent(BaseModel):
    event_id:      str      = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resource_id:   str      # "hvac:main", "co2_sensor:main"
    resource_type: str      # ResourceType value
    zone_id:       str      # "main"
    adapter:       str      # "mqtt"
    source_topic:  str      # raw origin — "basis/hvac/main/telemetry"
    payload:       dict     # normalized fields — preserved from original
    raw:           dict | None = None  # original payload, retained for debugging
```

Example instance (HVAC):

```json
{
  "event_id": "b3c2a1d0-...",
  "timestamp": "2025-01-01T12:00:00+00:00",
  "resource_id": "hvac:main",
  "resource_type": "hvac",
  "zone_id": "main",
  "adapter": "mqtt",
  "source_topic": "basis/hvac/main/telemetry",
  "payload": {
    "current_temperature": 22.3,
    "target_temperature": 21.0,
    "hvac_mode": "cooling",
    "fan_speed": "medium",
    "unit": "celsius"
  }
}
```

Example instance (CO₂ sensor):

```json
{
  "event_id": "c4d3b2e1-...",
  "timestamp": "2025-01-01T12:00:06+00:00",
  "resource_id": "co2_sensor:main",
  "resource_type": "co2_sensor",
  "zone_id": "main",
  "adapter": "mqtt",
  "source_topic": "basis/sensors/co2/telemetry",
  "payload": {
    "co2_level": 742,
    "unit": "ppm",
    "status": "elevated"
  }
}
```

### WebSocket broadcast message

The frontend currently receives `{type, topic, data}`. With normalization, this becomes:

```json
{
  "type": "update",
  "resource_id": "hvac:main",
  "topic": "basis/hvac/main/telemetry",
  "data": { ... payload ... },
  "timestamp": "2025-01-01T12:00:00+00:00"
}
```

`topic` is retained alongside `resource_id` to avoid a breaking change to the frontend. The frontend can migrate to keying on `resource_id` at its own pace.

---

## Normalized Command Schema

```python
# domain/events.py (CommandEvent)
class CommandEvent(BaseModel):
    command_id:    str      = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resource_id:   str      # "hvac:main"
    resource_type: str      # "hvac"
    zone_id:       str      # "main"
    action:        str      # ActionType value — "command"
    parameters:    dict     # action-specific payload
    subject_id:    str      # who issued it
    subject_type:  str      # SubjectType value
    subject_name:  str      # display name for logs and audit
    adapter:       str      # which adapter should dispatch this
    request_id:    str | None = None  # HTTP request ID for correlation
```

Example instance:

```json
{
  "command_id": "a1b2c3d4-...",
  "timestamp": "2025-01-01T12:00:00+00:00",
  "resource_id": "hvac:main",
  "resource_type": "hvac",
  "zone_id": "main",
  "action": "command",
  "parameters": {
    "target_temperature": 23.0
  },
  "subject_id": "a7b8c9d0-...",
  "subject_type": "human",
  "subject_name": "bob",
  "adapter": "mqtt",
  "request_id": "req_xyz"
}
```

The `parameters` field is intentionally open. The MQTT adapter's publisher translates `parameters` into the protocol-specific payload shape. A BACnet adapter would translate `parameters` into a BACnet WriteProperty request. The `CommandEvent` itself is protocol-agnostic.

---

## Audit Architecture

### Event schema

```python
# domain/events.py (AuditEvent)
class AuditEvent(BaseModel):
    event_id:      str      = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Who
    subject_id:    str
    subject_type:  str
    subject_name:  str

    # What
    action:        str                # ActionType value
    resource_id:   str | None = None
    resource_type: str | None = None
    zone_id:       str | None = None
    parameters:    dict = {}          # command parameters, if applicable

    # Outcome
    outcome:       str                # "allowed", "denied", "error"
    policy_name:   str | None = None  # which policy decided
    policy_reason: str | None = None  # human-readable reason

    # Context
    request_id:    str | None = None
    ip_address:    str | None = None
    metadata:      dict = {}
```

### Persistence model

SQLite via `aiosqlite`. A single file at `data/audit.db`, volume-mounted in Docker Compose. Schema is created by a versioned migration script run at startup.

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    timestamp     TEXT NOT NULL,       -- ISO 8601
    subject_id    TEXT NOT NULL,
    subject_type  TEXT NOT NULL,
    subject_name  TEXT NOT NULL,
    action        TEXT NOT NULL,
    resource_id   TEXT,
    resource_type TEXT,
    zone_id       TEXT,
    parameters    TEXT,               -- JSON
    outcome       TEXT NOT NULL,      -- "allowed", "denied", "error"
    policy_name   TEXT,
    policy_reason TEXT,
    request_id    TEXT,
    ip_address    TEXT,
    metadata      TEXT                -- JSON
);

CREATE INDEX IF NOT EXISTS ix_audit_subject   ON audit_events(subject_id);
CREATE INDEX IF NOT EXISTS ix_audit_resource  ON audit_events(resource_id);
CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_outcome   ON audit_events(outcome);
```

No ORM. Parameterized SQL. The schema is simple enough that raw aiosqlite is cleaner than adding SQLAlchemy.

### Where audit events are written

Two call sites cover the full audit surface:

**Authorization decisions** — inside `auth/dependencies.py`, after every `policy_engine.evaluate()` call. Both allowed and denied decisions are recorded. This captures every access attempt regardless of whether a command was actually dispatched.

**Command outcomes** — inside `routers/commands.py`, after `dispatcher.send_command()` completes. Records whether the command was delivered to the adapter or whether an error occurred. The `command_id` field links this record to the command event for correlation.

### API boundaries

```
GET  /api/audit                       # paginated list — admin only
GET  /api/audit?subject_id=bob        # filter by subject
GET  /api/audit?resource_id=hvac:main # filter by resource
GET  /api/audit?outcome=denied        # filter by outcome
GET  /api/audit?from=2025-01-01       # filter by date range
GET  /api/audit/{event_id}            # single record
```

Pagination via `limit` and `cursor` (event_id-based, not offset-based, for append-heavy tables). Default page size: 100 records.

---

## Future Identity Types

The `Subject` model's `SubjectType` enum documents the intended identity surface. The auth layer resolves subjects from whatever credential is presented — the policy engine and audit logger are unaware of the resolution mechanism.

**Device subjects** authenticate via mutual TLS client certificates or pre-shared MQTT credentials (when Mosquitto auth is added in Stage 6). The device's certificate CN or MQTT client ID becomes `subject.id`. Roles are replaced with capability tags in `subject.roles` (e.g., `["telemetry:publish", "command:receive"]`).

**Service subjects** authenticate via client credentials flow (OAuth2 `client_credentials` grant against Keycloak). A data pipeline, an EMS integration, or a third-party analytics platform acquires a short-lived token using a client secret. These tokens carry service-specific roles rather than user roles.

**Gateway subjects** represent a BASIS gateway process that sits between a legacy protocol network (BACnet, Modbus) and the MQTT broker. The gateway authenticates as a service subject. Every telemetry event it publishes carries both the gateway's identity and the originating device's identity in the `metadata` field.

**Automation agent subjects** are the most novel case: AI agents or automation scripts that take actions on behalf of a user or autonomously. They authenticate via delegated tokens (RFC 8693 token exchange) or via purpose-built agent credentials. The policy engine can apply tighter constraints to agent subjects — for example, agents may READ and COMMAND but not CONFIGURE, regardless of the roles on the delegating user's token. This constraint is expressed as a policy rule rather than hardcoded logic.

The critical design requirement is that every action taken by a non-human subject is auditable with the same fidelity as a human action. The audit record for an agent-issued command must carry both the agent's identity and, where applicable, the human identity that authorized the agent to act.

---

## Incremental Migration Plan

This plan is designed to be executed one stage at a time. Each stage is independently shippable — the system remains fully functional at every step. No stage requires touching the frontend unless explicitly noted.

### Stage 5 — Audit Logging (structural commit)

Create `audit/` with `logger.py` and `store.py`. Implement `StdoutAuditStore` as the initial backend (it writes to the uvicorn logger — identical to current behavior, just through a typed interface). Add `AuditEvent` to `domain/events.py`. Wire two call sites: auth dependency and command router. Add `routers/audit.py` stub returning 501. Add `data/` to Docker Compose volume mounts.

No behavior change. No breaking changes. Audit infrastructure is in place.

### Stage 5b — SQLite Audit Store

Implement `SqliteAuditStore`. Add schema migration at startup. Implement `/api/audit` endpoints with filter and pagination. Implement `GET /api/audit/{event_id}`. Wire to frontend as a new admin-only tab.

Carol can now query the full command history.

### Stage 6 — MQTT Security

Refactor `mqtt_client.py` → `adapters/mqtt/subscriber.py` and `mqtt_publisher.py` → `adapters/mqtt/publisher.py`. Add `adapters/base.py`. Add Mosquitto password file to `infra/mosquitto/`. Add per-service MQTT credentials to `docker-compose.yml` environment.

The API and simulator authenticate to the broker. Anonymous access disabled. Functional behavior unchanged.

### Stage 7 — Domain Model Introduction

Add `domain/` package. Add `Subject` model. Add `auth/subjects.py` with `token_to_subject()`. Change `get_current_user()` → `get_current_subject()` in `auth/dependencies.py`. Update route handlers to use `subject.name` instead of `user.get("preferred_username")`.

Add `policy/engine.py` and `policy/rbac.py`. Replace `require_role("operator", "admin")` with `require_action(ActionType.COMMAND)` in route handlers. Register `RoleBasedPolicy` at startup.

Authorization outcomes are identical. This is a pure internal refactor.

### Stage 7b — Normalized Events

Add `TelemetryEvent` and `CommandEvent` to `domain/events.py`. Add `telemetry/normalizer.py`. Update `adapters/mqtt/subscriber.py` to emit `TelemetryEvent` rather than raw dicts. Update WebSocket broadcast message to include `resource_id` alongside `topic`. Update `routers/commands.py` to build and dispatch `CommandEvent`.

Frontend continues to work unchanged (the `topic` field is preserved in broadcast messages).

### Stage 8 — Router Generalization

Rename `routers/controls.py` → `routers/commands.py`. Change path prefix from `/api/controls` to `/api/commands`. Update frontend `apiFetch` call from `/api/controls/hvac/main/setpoint` to `/api/commands/hvac/main/setpoint`. Add `commands/dispatcher.py`.

Add `routers/resources.py` with `GET /api/resources` returning the resource registry and `GET /api/zones` returning zone definitions.

One frontend path string changes. All behavior is preserved.

### Stage 9 — WebSocket Authentication

Add token validation to the WebSocket handshake via a `token` query parameter. On connection, resolve the subject and record a SUBSCRIBE audit event. On token expiry, close the connection with a 4001 code (client should re-initiate with a fresh token).

Frontend: update `useTelemetry()` to append `?token=${keycloak.token}` to the WebSocket URL and handle 4001 reconnection.

This closes the unauthenticated telemetry limitation documented in the Stage 4 README.

### Stage 10 — Second Adapter

Implement a BACnet/IP adapter or Modbus TCP adapter using `AdapterBase`. Register it alongside the MQTT adapter. Resources backed by the new adapter appear in `/api/resources` and can be commanded through the same `/api/commands/{type}/{zone}` path.

The identity model, policy engine, and audit logger require zero changes.

---

## Naming Improvements

The following renames improve long-term clarity. They are non-breaking changes when executed as part of the stage migrations above.

| Current | Proposed | Rationale |
|---|---|---|
| `auth.py` | `auth/` (package) | Splits JWKS, token, and subject concerns |
| `ws_manager.py` | `telemetry/broadcaster.py` | Describes function, not mechanism |
| `mqtt_client.py` | `adapters/mqtt/subscriber.py` | Positions MQTT as one adapter among many |
| `mqtt_publisher.py` | `adapters/mqtt/publisher.py` | Symmetric with subscriber |
| `routers/controls.py` | `routers/commands.py` | Commands is the generalized OT term |
| `routers/protected.py` | `routers/identity.py` | Protected is mechanism; identity is purpose |
| `/api/controls/` | `/api/commands/` | Consistent with domain terminology |
| `require_role(...)` | `require_action(...)` | Policy-based framing decoupled from RBAC |
| `get_current_user()` | `get_current_subject()` | User implies human; subjects are any identity |
| `SetpointCommand` | `HvacSetpointCommand` | Explicit resource type prefix for models |
| `VALID_ZONES` | Resource registry | Zones become a managed data structure |

---

## What Not To Build Yet

These are patterns that would cause premature complexity given the current stage.

**Message queue between adapter and policy layer.** The direct function call from adapter to broadcaster is correct for a single-process monolith. An in-process event bus (like `asyncio.Queue`) adds indirection without value until there is a demonstrated need for backpressure or fan-out to multiple consumers.

**gRPC or REST between internal modules.** Internal module boundaries should be Python imports, not network calls. Keep the API as a monolith until there is a specific deployment requirement (scaling, team isolation, or independent release cadence) that necessitates splitting.

**A rules engine DSL.** The `RoleBasedPolicy` class covers current needs. Introduce a DSL (YAML rules, Rego, Cedar) when the number of distinct policies or contributors makes inline Python unmanageable. That threshold is probably 5–10 distinct policy rules with non-trivial attribute conditions.

**Redis for telemetry snapshots.** The in-memory `_snapshot` dict in `broadcaster.py` is correct for a single-process deployment. Replace it with Redis only if BASIS is deployed in a horizontally-scaled API configuration, which is explicitly out of scope for Stages 1–9.

**User-managed resource configuration UI.** The resource registry can start as a hardcoded dict or a YAML file. A management UI and database-backed registry are appropriate when the number of resources grows beyond what can be managed in config files — not before.

**Async task framework (Celery, ARQ).** Command dispatch and audit writes are both lightweight and low-frequency (human-driven). `asyncio.to_thread` for MQTT publish and `aiosqlite` for audit writes are sufficient through Stage 9 at minimum.

---

*This document should be updated at each stage boundary to reflect the architectural state at that point. The migration plan above is the authoritative sequencing — individual stage READMEs document implementation details.*
