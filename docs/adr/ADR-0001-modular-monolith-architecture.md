# ADR-0001 — Modular Monolith Architecture

**Status:** Accepted  
**Date:** 2025-01-01  

## Context

Early in the project there was a natural question about service decomposition. BASIS has conceptually distinct concerns: authentication, authorization policy, MQTT transport, audit logging, telemetry routing, and the control API. These concerns could each be separated into independent services with their own processes and network boundaries.

The standard industry argument for microservices — independent deployability, team autonomy, per-service scaling — carries weight in large organizations with many teams and mature operational infrastructure. It carries much less weight for a platform with the following constraints:

- **OT environment target.** Operational technology environments are often air-gapped or network-restricted. Every additional service is another network endpoint to secure, another port to open, and another process to monitor. Operational overhead compounds quickly.
- **Single-operator deployment.** The target deployment profile is a single Docker Compose stack running on a single host, managed by a small team or a single operator. Microservices introduce distributed systems failure modes — partial startup, inter-service network latency, split-brain state — that are inappropriate for this context.
- **Early-stage platform.** Prematurely splitting a system into services before the domain boundaries are fully understood produces the wrong seams. Refactoring a distributed system is significantly harder than refactoring a monolith.

The alternative — a big-ball-of-mud monolith with no internal structure — was equally unappealing. It would resist future evolution and make the codebase difficult to reason about.

## Decision

BASIS is structured as a modular monolith: a single deployable process (`services/api`) with clean internal module boundaries that reflect the domain concepts.

The internal module structure enforces separation of concerns:

```
domain/       — canonical models (events, subject, resource). No project imports.
policy/       — authorization logic (engine, rbac, actions). Imports domain/ only.
audit/        — audit persistence and logging facade. Imports domain/ only.
auth.py       — JWT validation and authorization gateway. Imports policy/, audit/, domain/.
adapters/     — external protocol adapters (MQTT). Imports domain/, ws_manager.
routers/      — HTTP API endpoints. Import auth, domain, policy, adapters.
```

This import graph is enforced by convention and verified by inspection. No layer imports from a layer above it. `domain/` has no project imports at all — it is the base of the dependency graph.

These boundaries exist not because microservices were rejected, but because clean internal structure is valuable regardless of deployment topology. If a future operational requirement genuinely warrants splitting a module into its own service, the boundary already exists and the extraction will be straightforward.

## Consequences

**Accepted trade-offs:**
- A single process is a single failure domain. If the API process crashes, authentication, telemetry, controls, and audit all go down together. This is acceptable for the current deployment profile.
- Horizontal scaling requires careful thought — shared in-process state (the WebSocket broadcaster, the MQTT subscriber) does not trivially replicate across instances.

**Benefits realized:**
- Deployment is `docker compose up`. No service mesh, no inter-service authentication, no distributed tracing infrastructure required.
- The entire authorization path — JWT validation → subject resolution → policy evaluation → audit write — executes in a single process with no network hops.
- Internal refactors (e.g., migrating from `require_role()` to `require_action()`) touch multiple modules but require no inter-service contract negotiation.
- New contributors can understand the entire system by reading one codebase.
