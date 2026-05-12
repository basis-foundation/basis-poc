# Architecture Decision Records

This directory contains the Architecture Decision Records (ADRs) for the BASIS platform.

An ADR is a short document that captures an architecturally significant decision — one that affects the structure, behavior, or operational characteristics of the system — along with the reasoning behind it and the trade-offs accepted.

---

## Why BASIS Uses ADRs

BASIS is an evolving platform with a deliberate philosophy. Several of its architectural choices look unconventional from the outside — no Kubernetes, no PostgreSQL, no microservices, SQLite instead of a dedicated audit store. Without recorded reasoning, these choices can appear as omissions rather than decisions.

ADRs serve a practical purpose here:

- They document *why* a decision was made, not just *what* was decided.
- They prevent future contributors from relitigating settled questions without context.
- They make the architectural philosophy legible to anyone reading the codebase.
- They create a lightweight accountability mechanism: if a decision is revisited and reversed, a new ADR records that too.

This is not a governance process. There are no approval committees, no mandatory review cycles, and no tooling dependencies. An ADR is a markdown file in a directory.

---

## Format

Each ADR uses the following structure:

```
# ADR-XXXX — Title

**Status:** Accepted | Superseded by ADR-XXXX | Deprecated  
**Date:** YYYY-MM-DD  

## Context

What situation or constraint prompted this decision.

## Decision

What was decided.

## Consequences

What follows from this decision — including trade-offs accepted.
```

Keep ADRs focused and concise. The goal is to convey reasoning, not to write a design specification.

---

## Naming and Numbering Conventions

Files are named `ADR-XXXX-short-title.md` using four-digit zero-padded numbers. Numbers are assigned sequentially and never reused. If a decision is reversed, the original ADR is updated to `Superseded by ADR-XXXX` and a new ADR documents the reversal.

Numbers do not imply priority or importance — they reflect the order in which decisions were recorded.

---

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-0001](ADR-0001-modular-monolith-architecture.md) | Modular Monolith Architecture | Accepted |
| [ADR-0002](ADR-0002-sqlite-audit-persistence.md) | SQLite Audit Persistence | Accepted |
| [ADR-0003](ADR-0003-mqtt-as-transport-layer.md) | MQTT as Transport Layer Only | Accepted |
| [ADR-0004](ADR-0004-action-based-authorization.md) | Action-Based Authorization Model | Accepted |
| [ADR-0005](ADR-0005-subject-resource-event-normalization.md) | Subject, Resource, and Event Normalization | Accepted |
| [ADR-0006](ADR-0006-local-first-architecture.md) | Local-First Architecture Philosophy | Accepted |
| [ADR-0007](ADR-0007-wire-compatibility-during-refactors.md) | Preserve Wire Compatibility During Internal Refactors | Accepted |
| [ADR-0008](ADR-0008-no-kubernetes-dependency.md) | No Kubernetes Dependency | Accepted |

---

## Proposing a New ADR

Create a new file following the naming convention, write a draft using the format above, and open a pull request. The bar for acceptance is that the decision is architecturally significant and the reasoning is clearly stated. Minor implementation choices do not warrant ADRs.

If you are revisiting an existing ADR — because circumstances have changed, or because the original decision is no longer correct — write a new ADR that explicitly references and supersedes the original.
