# policy — module-level singleton, same pattern as audit/__init__.py.
#
# Import this anywhere policy evaluation is needed:
#   from policy import engine
#   result = engine.evaluate(subject, action)
#
# The singleton is initialized once at import time with all active policies.
# Policies are evaluated in order — earlier policies have higher precedence.
#
# To add a new policy type, append an instance to the list below.
# No call-site changes are required.

from policy.engine import PolicyEngine
from policy.rbac import RoleBasedPolicy

# Stage 7: single policy. Future stages append before RoleBasedPolicy
# to intercept actions with higher-priority context-aware rules.
engine = PolicyEngine(policies=[RoleBasedPolicy()])
