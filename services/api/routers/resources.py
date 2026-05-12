"""
BASIS — Resource Registry Endpoints
Stage 8: Read-only view of the static OT resource registry.

These endpoints expose the normalized resource model introduced in domain/resource.py.
They are informational — no writes, no mutations, no database.

Why expose the registry via API
────────────────────────────────
The resource registry is what makes BASIS a generalized OT identity platform
rather than a one-off HVAC demo. Exposing it via API lets:
  - The frontend enumerate available zones and resource types dynamically
    (Stage 9: zone selector UI)
  - API consumers build resource-aware clients without hardcoding resource IDs
  - Operators verify which resources are registered before sending commands
  - Tests assert that expected resources exist without inspecting source code

Authorization
─────────────
Reading the resource registry requires any authenticated identity (viewer or above).
The OT topology is not sensitive information in the context of a PoC — any
authenticated user should be able to see what devices exist.
Unauthorized callers (no token, expired token) receive 401 as normal.

Endpoints
─────────
  GET /api/resources                   — list all resources (optional ?type= filter)
  GET /api/resources/{resource_id}     — get a single resource by normalized ID
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import require_action
from domain.resource import Resource, ResourceType, list_resources, resolve_resource
from domain.subject import Subject
from policy import actions

router = APIRouter(prefix="/api/resources", tags=["resources"])


# ── List resources ────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="List registered OT resources",
    description=(
        "Returns all resources registered in the static resource registry.\n\n"
        "Use the optional `type` query parameter to filter by resource type "
        "(e.g., `?type=hvac`, `?type=sensor`, `?type=zone`).\n\n"
        "**Required action:** `read:resources` (viewer, operator, or admin role)."
    ),
)
async def list_all_resources(
    type: Optional[str] = Query(
        default=None,
        description="Filter by resource type: hvac | sensor | zone | device | gateway",
        examples=["hvac"],
    ),
    _subject: Subject = Depends(require_action(actions.READ_RESOURCES)),
) -> dict:
    # Validate and resolve the optional type filter
    resource_type: Optional[ResourceType] = None
    if type is not None:
        try:
            resource_type = ResourceType(type.lower())
        except ValueError:
            valid = [t.value for t in ResourceType]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown resource type '{type}'. Valid types: {valid}",
            )

    resources = list_resources(resource_type)
    return {
        "resources": [_resource_dict(r) for r in resources],
        "count":     len(resources),
        "filter":    {"type": type} if type else {},
    }


# ── Get single resource ───────────────────────────────────────────────────────

@router.get(
    "/{resource_id:path}",
    summary="Get a resource by ID",
    description=(
        "Returns a single resource by its normalized ID "
        "(e.g., `hvac:main`, `sensor:co2`, `zone:main`).\n\n"
        "**Required action:** `read:resources` (viewer, operator, or admin role)."
    ),
)
async def get_resource(
    resource_id: str,
    _subject: Subject = Depends(require_action(actions.READ_RESOURCES)),
) -> dict:
    resource = resolve_resource(resource_id)
    if resource is None:
        all_ids = [r.id for r in list_resources()]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Resource '{resource_id}' not found in registry. "
                f"Registered resources: {all_ids}"
            ),
        )
    return _resource_dict(resource)


# ── Serialization helper ──────────────────────────────────────────────────────

def _resource_dict(resource: Resource) -> dict:
    """Serialize a Resource to a plain dict for API responses."""
    return {
        "id":          resource.id,
        "type":        resource.type.value,
        "name":        resource.name,
        "zone":        resource.zone,
        "description": resource.description,
    }
