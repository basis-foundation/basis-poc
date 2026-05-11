"""
BASIS — Policy Engine
Stage 7: Evaluates whether a Subject may perform an Action on a Resource.

Why PolicyEngine exists
────────────────────────
Prior stages merged two distinct concerns inside require_role():
  1. Who is this?   (token validation → JWT payload)
  2. What may they do?  (role check → allow/deny)

PolicyEngine separates concern 2 into its own layer:

  auth.py           — answers "who is this?"  (token → Subject)
  policy/engine.py  — answers "what may they do?"  (Subject + Action → allow/deny)

This separation is important for an OT identity platform because authorization
decisions will grow in complexity before authentication does:
  - Time-of-day restrictions on commands
  - Zone-scoped role grants (Stage 8)
  - Emergency override modes
  - Device identity policies for non-human subjects

Each of those is a new Policy in the chain. None of them touch auth.py or any router.

Chain-of-responsibility pattern
────────────────────────────────
PolicyEngine.evaluate() walks a list of Policy objects. Each policy either:
  - Returns a PolicyResult  → evaluation stops, this result is used.
  - Returns None            → "I have no opinion; pass to the next policy."

The first policy to return a non-None result wins. If no policy handles the
action, the engine returns DENY. This "fail closed" default is intentional —
an unrecognized action should never silently succeed.

PolicyResult
────────────
A typed result object prevents accidentally treating a denial as a success
(which can happen with truthy None returns or bare boolean returns).
The evaluated_by field names the policy class that produced the result,
which is useful in audit logs and debugging multi-policy chains.
"""

import logging
from typing import Optional, Protocol, runtime_checkable

from domain.subject import Subject

log = logging.getLogger("basis.policy.engine")


class PolicyResult:
    """
    The outcome of a single policy evaluation.

    Attributes:
      allowed      — True if the action is permitted.
      reason       — Human-readable explanation. Always present.
                     Allowed results: brief confirmation.
                     Denied results: what was required vs. what was held.
      evaluated_by — Name of the Policy class that produced this result.
                     Appears in audit logs and debug output.
    """
    __slots__ = ("allowed", "reason", "evaluated_by")

    def __init__(self, *, allowed: bool, reason: str, evaluated_by: str) -> None:
        self.allowed      = allowed
        self.reason       = reason
        self.evaluated_by = evaluated_by

    def __repr__(self) -> str:
        verdict = "ALLOW" if self.allowed else "DENY"
        return f"PolicyResult({verdict}, policy={self.evaluated_by!r}, reason={self.reason!r})"


@runtime_checkable
class Policy(Protocol):
    """
    Interface for all BASIS policy implementations.

    Implementors must define evaluate(). The method returns:
      PolicyResult — this policy has an opinion about the action (allow or deny).
      None         — this policy does not cover this action; pass to the next policy.

    Returning None is the correct behavior when a policy does not recognize
    the action — it means "I have no opinion; ask someone else." A policy
    should never return DENY for an action it does not recognize, because
    that would prevent any downstream policy from allowing it.
    """

    def evaluate(
        self,
        subject: Subject,
        action: str,
        resource_id: Optional[str] = None,
    ) -> Optional[PolicyResult]:
        ...


class PolicyEngine:
    """
    Evaluates authorization requests by walking a list of Policy implementations.

    Usage:
        engine = PolicyEngine(policies=[RoleBasedPolicy()])
        result = engine.evaluate(subject, "write:hvac:setpoint", resource_id="hvac:main")
        if not result.allowed:
            raise HTTPException(403, result.reason)

    Chain behavior:
        Policies are evaluated in the order they appear in the list.
        First non-None PolicyResult wins.
        If no policy handles the action → default DENY (fail closed).

    Future extensions — add policies before RoleBasedPolicy for higher precedence:
        PolicyEngine(policies=[
            ZoneScopePolicy(),        # Stage 8: check zone-level grants
            TimeWindowPolicy(),       # Future: restrict commands to business hours
            EmergencyOverridePolicy(),# Future: bypass normal policy in alarm state
            RoleBasedPolicy(),        # Current: check realm roles
        ])
    """

    def __init__(self, policies: list) -> None:
        self._policies = list(policies)
        log.info(
            "PolicyEngine initialized — %d policy(ies): %s",
            len(self._policies),
            [type(p).__name__ for p in self._policies],
        )

    def evaluate(
        self,
        subject: Subject,
        action: str,
        resource_id: Optional[str] = None,
    ) -> PolicyResult:
        """
        Evaluate subject + action + optional resource against the policy chain.

        Returns the first non-None PolicyResult from the chain.
        Returns a default DENY if no policy claims the action.
        """
        for policy in self._policies:
            result = policy.evaluate(subject, action, resource_id)
            if result is not None:
                log.debug(
                    "policy=%-20s  subject=%-12s  action=%-28s  resource=%-12s  %s",
                    result.evaluated_by,
                    subject.name,
                    action,
                    resource_id or "-",
                    "ALLOW" if result.allowed else "DENY",
                )
                return result

        # Fail closed: no policy handled this action — this is a config error
        reason = (
            f"No policy is registered for action '{action}'. "
            "All valid actions must be covered by at least one policy. "
            "Add the action to policy/actions.py and policy/rbac.py."
        )
        log.error("PolicyEngine: uncovered action '%s' for subject '%s'", action, subject.name)
        return PolicyResult(allowed=False, reason=reason, evaluated_by="PolicyEngine")
