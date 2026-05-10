"""
Basis Foundation — Role-Protected Endpoints
Stage 2: Demonstrates JWT validation and role-based access control.

Role hierarchy for these endpoints:
  viewer  → can call /api/viewer only
  operator → can call /api/viewer and /api/operator
  admin   → can call all three

All endpoints require a valid Keycloak JWT in the Authorization header.
Return 401 if no/invalid token, 403 if token is valid but role is wrong.
"""

from fastapi import APIRouter, Depends
from auth import get_current_user, require_role, get_roles

router = APIRouter(prefix="/api", tags=["protected"])


# ── Identity ──────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    summary="Current user identity",
    description="Returns the calling user's identity and roles. Requires any valid token.",
)
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    return {
        "sub": user.get("sub"),
        "username": user.get("preferred_username"),
        "email": user.get("email"),
        "name": user.get("name"),
        "roles": get_roles(user),
        "issuer": user.get("iss"),
        "expires_at": user.get("exp"),
    }


# ── Viewer endpoint ───────────────────────────────────────────────────────────
@router.get(
    "/viewer",
    summary="Viewer-level access",
    description="Accessible to: **viewer**, operator, admin.",
)
async def viewer_endpoint(
    user: dict = Depends(require_role("viewer", "operator", "admin")),
) -> dict:
    return {
        "endpoint": "/api/viewer",
        "access_level": "viewer",
        "accessible_to": ["viewer", "operator", "admin"],
        "message": "Telemetry dashboards and read-only data will be available here.",
        "caller": {
            "username": user.get("preferred_username"),
            "roles": get_roles(user),
        },
    }


# ── Operator endpoint ─────────────────────────────────────────────────────────
@router.get(
    "/operator",
    summary="Operator-level access",
    description="Accessible to: operator, **admin**. Denied for viewer.",
)
async def operator_endpoint(
    user: dict = Depends(require_role("operator", "admin")),
) -> dict:
    return {
        "endpoint": "/api/operator",
        "access_level": "operator",
        "accessible_to": ["operator", "admin"],
        "message": "HVAC control commands and setpoint changes will be handled here.",
        "caller": {
            "username": user.get("preferred_username"),
            "roles": get_roles(user),
        },
    }


# ── Admin endpoint ────────────────────────────────────────────────────────────
@router.get(
    "/admin",
    summary="Admin-level access",
    description="Accessible to: **admin** only. Denied for viewer and operator.",
)
async def admin_endpoint(
    user: dict = Depends(require_role("admin")),
) -> dict:
    return {
        "endpoint": "/api/admin",
        "access_level": "admin",
        "accessible_to": ["admin"],
        "message": "Audit logs, user management, and system configuration will live here.",
        "caller": {
            "username": user.get("preferred_username"),
            "roles": get_roles(user),
        },
    }
