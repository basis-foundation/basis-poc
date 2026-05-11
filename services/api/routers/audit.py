"""
BASIS — Audit Log Endpoints
Stage 5: Stub only. Returns 501 Not Implemented.
Stage 7: Migrated from require_role("admin") to require_action(READ_AUDIT_LOG).

The authorization contract is enforced now even as a stub:
  alice (viewer) → 403
  bob (operator) → 403
  carol (admin)  → 501 (authorized, but store query not yet implemented)

Stage 5b will implement:
  GET /api/audit                 — paginated list (admin only)
  GET /api/audit?subject_id=bob  — filter by subject
  GET /api/audit?outcome=denied  — filter by outcome
  GET /api/audit/{event_id}      — single record
"""

from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_action
from domain.subject import Subject
from policy import actions

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get(
    "",
    summary="List audit events",
    description=(
        "Returns paginated audit log entries.\n\n"
        "**Required action:** `read:audit:log` (admin role only)\n\n"
        "⚠ Not yet implemented — returns 501 until Stage 5b."
    ),
)
async def list_audit_events(
    _subject: Subject = Depends(require_action(actions.READ_AUDIT_LOG)),
) -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Audit log query API is not yet implemented. "
            "Audit events are currently written to the API container logs. "
            "Run: docker compose logs api | grep AUDIT"
        ),
    )
