"""
Basis Foundation — Role-Protected Endpoints
Stage 2: Demonstrates JWT validation and role-based access control.
Stage 7: Migrated from require_role() to require_action() + Subject.
         Authorization now flows through PolicyEngine → RoleBasedPolicy.
         External API behavior is identical — same endpoints, same 401/403 responses.

Role hierarchy for these endpoints (unchanged):
  viewer   → can call /api/viewer only
  operator → can call /api/viewer and /api/operator
  admin    → can call all three

All endpoints require a valid Keycloak JWT in the Authorization header.
Returns 401 if no/invalid token, 403 if token is valid but action is denied.
"""

from fastapi import APIRouter, Depends

from auth import get_current_user, get_current_subject, require_action, get_roles
from domain.subject import Subject
from policy import actions

router = APIRouter(prefix="/api", tags=["protected"])


# ── Identity ──────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    summary="Current user identity",
    description=(
        "Returns the calling user's identity, roles, and subject type. "
        "Requires any valid token — no specific role needed."
    ),
)
async def get_me(
    payload: dict = Depends(get_current_user),
) -> dict:
    """
    /api/me uses get_current_user (raw JWT payload) rather than get_current_subject
    because it needs raw JWT fields that Subject does not carry: iss and exp.
    The subject_type field is added by resolving to Subject for display purposes.
    """
    from domain.subject import subject_from_jwt
    subject = subject_from_jwt(payload)
    return {
        "sub":          subject.id,
        "username":     subject.name,
        "email":        subject.email,
        "name":         payload.get("name"),        # full display name from JWT
        "roles":        subject.roles,
        "subject_type": subject.type.value,         # "human" — visible in API response
        "issuer":       payload.get("iss"),
        "expires_at":   payload.get("exp"),
    }


# ── Viewer endpoint ───────────────────────────────────────────────────────────
@router.get(
    "/viewer",
    summary="Viewer-level access",
    description=(
        "Accessible to: **viewer**, operator, admin.\n\n"
        "Action: `read:api:viewer`"
    ),
)
async def viewer_endpoint(
    subject: Subject = Depends(require_action(actions.ACCESS_VIEWER_API)),
) -> dict:
    return {
        "endpoint":      "/api/viewer",
        "access_level":  "viewer",
        "accessible_to": ["viewer", "operator", "admin"],
        "message":       "Telemetry dashboards and read-only data will be available here.",
        "caller": {
            "username":     subject.name,
            "roles":        subject.roles,
            "subject_type": subject.type.value,
        },
    }


# ── Operator endpoint ─────────────────────────────────────────────────────────
@router.get(
    "/operator",
    summary="Operator-level access",
    description=(
        "Accessible to: operator, **admin**. Denied for viewer.\n\n"
        "Action: `read:api:operator`"
    ),
)
async def operator_endpoint(
    subject: Subject = Depends(require_action(actions.ACCESS_OPERATOR_API)),
) -> dict:
    return {
        "endpoint":      "/api/operator",
        "access_level":  "operator",
        "accessible_to": ["operator", "admin"],
        "message":       "HVAC control commands and setpoint changes will be handled here.",
        "caller": {
            "username":     subject.name,
            "roles":        subject.roles,
            "subject_type": subject.type.value,
        },
    }


# ── Admin endpoint ────────────────────────────────────────────────────────────
@router.get(
    "/admin",
    summary="Admin-level access",
    description=(
        "Accessible to: **admin** only. Denied for viewer and operator.\n\n"
        "Action: `read:api:admin`"
    ),
)
async def admin_endpoint(
    subject: Subject = Depends(require_action(actions.ACCESS_ADMIN_API)),
) -> dict:
    return {
        "endpoint":      "/api/admin",
        "access_level":  "admin",
        "accessible_to": ["admin"],
        "message":       "Audit logs, user management, and system configuration will live here.",
        "caller": {
            "username":     subject.name,
            "roles":        subject.roles,
            "subject_type": subject.type.value,
        },
    }
