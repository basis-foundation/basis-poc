"""
BASIS — Audit Log Endpoints
Stage 5: Stub only. Returns 501 Not Implemented.

Stage 5b will implement:
  GET /api/audit                 — paginated list (admin only)
  GET /api/audit?subject_id=bob  — filter by subject
  GET /api/audit?outcome=denied  — filter by outcome
  GET /api/audit/{event_id}      — single record

All endpoints require the admin role. The requirement is enforced here even
as a stub so that the authorization contract is established before data exists.
alice (viewer) and bob (operator) will receive 403, not 501.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_role

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get(
    "",
    summary="List audit events",
    description=(
        "Returns paginated audit log entries.\n\n"
        "**Required role:** `admin`\n\n"
        "⚠ Not yet implemented — returns 501 until Stage 5b."
    ),
)
async def list_audit_events(
    _user: dict = Depends(require_role("admin")),
) -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Audit log query API is not yet implemented. "
            "Audit events are currently written to the API container logs. "
            "Run: docker compose logs api | grep AUDIT"
        ),
    )
