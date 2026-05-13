"""
BASIS — Action Constants
Stage 7:  Defines the named actions that subjects may request in BASIS.
Stage 8:  READ_RESOURCES action added for the resource registry endpoint.
Stage 9:  SUBSCRIBE_TELEMETRY and DISCONNECT_TELEMETRY added for the authenticated
          WebSocket telemetry gateway.
Stage 10: WRITE_MODBUS_SETPOINT added for the Modbus TCP adapter command path.
          This action name deliberately encodes the protocol ("modbus") so that
          audit records are self-describing — an operator reading the audit log
          can distinguish a Modbus setpoint write from an HVAC setpoint write
          without inspecting the detail dict.

Why named actions instead of role strings at endpoints
───────────────────────────────────────────────────────
Prior stages called require_role("operator", "admin") directly at each endpoint,
coupling the route to the current role structure. This creates a maintenance
problem: if a new "supervisor" role should be allowed to send HVAC commands,
every endpoint that checks for "operator" must be found and updated.

Named actions invert that relationship. An endpoint declares *what it does*:
  require_action(WRITE_HVAC_SETPOINT)

The policy layer decides *who may do it*:
  WRITE_HVAC_SETPOINT → {"operator", "admin"}   (in rbac.py)

Adding a new role that can send commands means one change in rbac.py. The router
is untouched. The action name is what appears in the audit log — it is more
meaningful than "api_access" and survives role-model refactors without losing
audit trail continuity.

Naming convention
─────────────────
  "<verb>:<domain>[:<object>]"  —  colon-separated, lowercase

  Verb:   read | write | delete | execute
  Domain: api | hvac | audit | telemetry | identity | ...
  Object: (specific resource type if needed)

  Example:  write:hvac:setpoint  →  "write a setpoint to an HVAC zone"
            read:audit:log        →  "read records from the audit log"

Stability requirement
─────────────────────
Action constants appear verbatim in audit log records. Renaming a constant
breaks audit trail continuity — historical log entries will no longer match
code searches. Treat action names as stable identifiers once they ship.
To deprecate an action, leave the old constant with a comment and add the new one.
"""

# ── API access actions ─────────────────────────────────────────────────────────
# Used by the role-demonstration endpoints in routers/protected.py.
# These mirror the existing role hierarchy: viewer ⊂ operator ⊂ admin.

ACCESS_VIEWER_API   = "read:api:viewer"    # /api/viewer  — viewer, operator, admin
ACCESS_OPERATOR_API = "read:api:operator"  # /api/operator — operator, admin
ACCESS_ADMIN_API    = "read:api:admin"     # /api/admin   — admin only

# ── HVAC control actions ───────────────────────────────────────────────────────
# Issued when a subject submits a setpoint change via the controls router.
# Stage 8 will add zone-scoped variants: write:hvac:setpoint:zone/{zone}

WRITE_HVAC_SETPOINT = "write:hvac:setpoint"

# ── Resource actions ───────────────────────────────────────────────────────────
# Reading the resource registry is available to all authenticated users.
# The registry is static (no database) so exposure carries no significant risk.
# This action gives the frontend and API consumers visibility into the OT topology.

READ_RESOURCES = "read:resources"

# ── Audit actions ──────────────────────────────────────────────────────────────
# Querying the audit log is an admin-only operation.
# The audit endpoint returns 501 until Stage 5b — the authorization gate
# is enforced now so the contract is established before data exists.

READ_AUDIT_LOG = "read:audit:log"

# ── Telemetry subscription actions ────────────────────────────────────────────
# Stage 9: Authenticated telemetry gateway.
#
# SUBSCRIBE_TELEMETRY is evaluated by the PolicyEngine at WebSocket connection
# time. All three OT roles (viewer, operator, admin) may subscribe — telemetry
# is read-only. A denied subscription is recorded in the audit log with
# outcome="denied" before the WebSocket is closed with code 4000.
#
# DISCONNECT_TELEMETRY is NOT enforced by require_action(). It is used only
# as the action name in the audit record emitted when a session ends. Recording
# disconnects in the audit log gives operators a complete session lifecycle view:
#   SUBSCRIBE allowed  →  (session active for N seconds)  →  DISCONNECT
#
# These names appear verbatim in audit records. They must remain stable.
# Treat them as external identifiers, not internal implementation details.

SUBSCRIBE_TELEMETRY  = "subscribe:telemetry"
DISCONNECT_TELEMETRY = "disconnect:telemetry"

# ── Modbus adapter actions ─────────────────────────────────────────────────────
# Stage 10: Authenticated command path for the Modbus TCP adapter.
#
# WRITE_MODBUS_SETPOINT gates all holding-register writes: chiller supply
# temperature setpoint (HR 40001) and pump speed (HR 40101). A single action
# covers both writes because both require the same minimum role (operator) and
# the specific register written is captured in the audit detail dict.
#
# This follows the same pattern as WRITE_HVAC_SETPOINT: one action per
# authorization boundary, not one action per register. The identity model,
# PolicyEngine, and audit logger are unchanged by the Modbus adapter.

WRITE_MODBUS_SETPOINT = "write:modbus:setpoint"
