"""
BASIS — Role-Based Access Control Policy
Stage 7: Maps named actions to the realm roles that may perform them.
Stage 8: READ_RESOURCES added — viewer, operator, and admin may read the resource registry.
Stage 9: SUBSCRIBE_TELEMETRY added — all three OT roles may connect to the telemetry gateway.

This is the authoritative role model for BASIS. It replaces the scattered
require_role("operator", "admin") calls that previously lived in each router.

Before Stage 7 (scattered):
  protected.py:   Depends(require_role("viewer", "operator", "admin"))
  protected.py:   Depends(require_role("operator", "admin"))
  protected.py:   Depends(require_role("admin"))
  controls.py:    Depends(require_role("operator", "admin"))
  audit.py:       Depends(require_role("admin"))

After Stage 7 (centralized here):
  _ACTION_ROLES = {
      ACCESS_VIEWER_API:   {"viewer", "operator", "admin"},
      ACCESS_OPERATOR_API: {"operator", "admin"},
      ACCESS_ADMIN_API:    {"admin"},
      WRITE_HVAC_SETPOINT: {"operator", "admin"},
      READ_AUDIT_LOG:      {"admin"},
  }

Adding a new role (e.g., "supervisor" who can send HVAC commands):
  Before: find and update every require_role() call across all routers.
  After:  add "supervisor" to WRITE_HVAC_SETPOINT's set. One line. Done.

Design constraints
──────────────────
- This policy only handles HUMAN subjects (the current authentication path).
  DEVICE, SERVICE, GATEWAY, AGENT subjects return None and pass to the next
  policy in the chain. This allows future device-identity policies to handle
  those types without modifying RoleBasedPolicy.

- The policy preserves Stage 6 behavior exactly. Same actions, same roles,
  same outcomes. The only change is where the logic lives.

- Returning None for an unrecognized action (rather than DENY) is correct
  because another policy in the chain might handle it. A DENY from this
  method would short-circuit legitimate future policies.
"""

import logging
from typing import Optional

from domain.subject import Subject, SubjectType
from policy import actions
from policy.engine import PolicyResult

log = logging.getLogger("basis.policy.rbac")

# ── Action → required roles ────────────────────────────────────────────────────
#
# This table is the single source of truth for role-based authorization in BASIS.
#
# To add a new action: define it in policy/actions.py, add it here.
# To grant a new role: add the role name to the appropriate set(s).
# To restrict an action: remove roles from the set.
#
# Important: action names must match exactly what routes pass to require_action().
# They appear verbatim in audit logs — keep them stable.
#
_ACTION_ROLES: dict[str, set[str]] = {
    # ── API access (role-demonstration endpoints) ──────────────────────────────
    actions.ACCESS_VIEWER_API:   {"viewer", "operator", "admin"},
    actions.ACCESS_OPERATOR_API: {"operator", "admin"},
    actions.ACCESS_ADMIN_API:    {"admin"},

    # ── HVAC control ───────────────────────────────────────────────────────────
    actions.WRITE_HVAC_SETPOINT: {"operator", "admin"},

    # ── Resource registry ──────────────────────────────────────────────────────
    actions.READ_RESOURCES:      {"viewer", "operator", "admin"},

    # ── Audit log access ───────────────────────────────────────────────────────
    actions.READ_AUDIT_LOG:      {"admin"},

    # ── Telemetry subscription ─────────────────────────────────────────────────
    # All authenticated OT roles may subscribe. Telemetry is read-only and
    # visible to every operator, viewer, and admin by design. Restricting
    # telemetry access to operators would limit the ability of viewers to
    # monitor system state — the primary use case for the viewer role.
    # Stage 10+ zone-scoped policies will allow finer-grained restriction
    # without changing this entry.
    actions.SUBSCRIBE_TELEMETRY: {"viewer", "operator", "admin"},
}


class RoleBasedPolicy:
    """
    Authorization policy: allow/deny actions based on realm roles.

    Implements the chain-of-responsibility Policy protocol from policy/engine.py.

    evaluate() behavior:
      Returns PolicyResult(allowed=True)   — subject holds a required role.
      Returns PolicyResult(allowed=False)  — subject authenticated but lacks role.
      Returns None                         — action not in table, or subject is
                                             not HUMAN (pass to next policy).
    """

    def evaluate(
        self,
        subject: Subject,
        action: str,
        resource_id: Optional[str] = None,
    ) -> Optional[PolicyResult]:
        name = type(self).__name__

        # Only handle human subjects — other types pass through.
        # A DEVICE subject, for example, is handled by a future DeviceIdentityPolicy.
        if subject.type != SubjectType.HUMAN:
            log.debug(
                "%s: skipping subject type '%s' for action '%s'",
                name, subject.type.value, action,
            )
            return None

        required = _ACTION_ROLES.get(action)

        # Action not in this policy's table — pass to the next policy in the chain.
        # Do NOT return DENY here: another policy might handle this action.
        if required is None:
            return None

        if subject.has_role(*required):
            return PolicyResult(
                allowed=True,
                reason=(
                    f"Allowed. Subject '{subject.name}' holds a role "
                    f"permitted for '{action}'."
                ),
                evaluated_by=name,
            )

        return PolicyResult(
            allowed=False,
            reason=(
                f"Access denied. Action '{action}' requires one of: "
                f"{sorted(required)}. "
                f"Subject '{subject.name}' holds: "
                f"{sorted(subject.roles) or ['(none)']}."
            ),
            evaluated_by=name,
        )
