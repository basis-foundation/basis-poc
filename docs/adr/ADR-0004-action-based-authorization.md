# ADR-0004 — Action-Based Authorization Model

**Status:** Accepted  
**Date:** 2025-04-01  

## Context

Early stages of BASIS enforced authorization by checking role membership directly at each endpoint:

```python
async def set_hvac_setpoint(..., roles=Depends(require_role("operator", "admin"))):
    ...
```

This approach is direct and easy to read, but it couples the authorization model to the role structure at every call site. When a new role needs access to an existing endpoint, the endpoint must be found and modified. When the same endpoint is accessed by multiple callers with different justifications, there is no way to distinguish those cases in the audit trail. The audit log records `roles=["operator"]` but not `action=write:hvac:setpoint` — the role is an attribute of identity, not a description of intent.

The deeper problem is the direction of the authorization question. Role-based checks at endpoints ask: "does this user have role X?" The better question is: "is this user permitted to perform action A?" The distinction matters when roles proliferate, when non-human subjects are introduced, or when per-resource policy is needed. All of those cases become progressively harder to manage with role checks scattered across endpoint definitions.

## Decision

Authorization is expressed as named actions rather than role membership checks. Each protected endpoint declares what it does:

```python
subject = Depends(require_action(actions.WRITE_HVAC_SETPOINT))
```

The policy layer (`policy/rbac.py`) maps actions to permitted roles:

```python
_ACTION_ROLES = {
    actions.WRITE_HVAC_SETPOINT: {"operator", "admin"},
    actions.READ_AUDIT_LOG:      {"admin"},
    actions.READ_RESOURCES:      {"viewer", "operator", "admin"},
}
```

This mapping is the single location where role-to-action relationships are defined. Adding a new role that can send HVAC commands requires one change in `policy/rbac.py` — no endpoint files change.

`require_action()` produces a `Subject` object from the validated JWT, evaluates the action against the `PolicyEngine`, records an `AuditEvent` with the named action (regardless of outcome), and either returns the subject to the handler or raises `403`. The endpoint receives a typed `Subject`, not a raw JWT dict.

Action names follow the convention `<verb>:<domain>[:<object>]` — e.g., `write:hvac:setpoint`, `read:audit:log`. They are stable string constants defined in `policy/actions.py`. Because they appear verbatim in audit records, renaming a constant would break audit trail continuity; action names are treated as stable identifiers once in use.

The `PolicyEngine` uses a chain-of-responsibility pattern. `RoleBasedPolicy` is the current implementation. Future policies (attribute-based, zone-scoped, time-windowed) can be added to the chain without modifying existing policy implementations or call sites.

## Consequences

**Accepted trade-offs:**
- Named actions require maintaining the action-to-role mapping in `policy/rbac.py`. This is an intentional centralization — the coupling that was previously distributed across all endpoint files is now concentrated in one place.
- Action names are stable by design, which means deprecated actions must be kept as constants with documentation rather than deleted.

**Benefits realized:**
- The authorization model is readable from a single file (`policy/rbac.py`) rather than being reconstructed by searching all endpoint definitions.
- The audit trail records what the subject intended to do (`action=write:hvac:setpoint`) rather than who they were (`roles=["operator"]`). This is more meaningful for security review.
- Non-human subjects (devices, services, gateways) can be authorized for specific actions without fitting into the human role hierarchy. The policy chain evaluates the subject type and applies appropriate logic.
- Zone-scoped and resource-scoped authorization — "operator may write setpoints only for zones they manage" — is expressible as an additional `Policy` implementation without modifying existing endpoints or the `RoleBasedPolicy`.

See also: [ADR-0005](ADR-0005-subject-resource-event-normalization.md).
