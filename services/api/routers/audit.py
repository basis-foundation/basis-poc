"""
BASIS — Audit Log Endpoints
Stage 5:  Stub only. Returns 501 Not Implemented.
Stage 7:  Migrated from require_role("admin") to require_action(READ_AUDIT_LOG).
Stage 5b: Full implementation. GET /api/audit with filters; GET /api/audit/{event_id}.

Authorization
─────────────
  alice (viewer)   → 403 Forbidden
  bob (operator)   → 403 Forbidden
  carol (admin)    → 200 OK

This is intentional: the audit log is the security record of all actions
performed in BASIS. Restricting reads to admins prevents subjects from
querying their own history to probe what is and is not being logged.

Endpoints
─────────
  GET /api/audit                          — list events, newest first (default limit 50)
  GET /api/audit?subject_id=<id>          — filter by JWT sub claim
  GET /api/audit?outcome=denied           — filter by outcome (allowed|denied|error)
  GET /api/audit?action=write:hvac:setpoint — filter by policy action name
  GET /api/audit?resource_id=hvac:main    — filter by normalized resource ID
  GET /api/audit?limit=100                — override result count (max 500)
  GET /api/audit/{event_id}               — single event by UUID

Filters are AND-combined. All filters are optional.
Results are ordered newest-first (timestamp DESC).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from audit import sqlite_store
from auth import require_action
from domain.subject import Subject
from policy import actions

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ── List audit events ─────────────────────────────────────────────────────────

@router.get(
    "",
    summary="List audit events",
    description=(
        "Returns audit log entries from the SQLite store, newest first.\n\n"
        "All filter parameters are optional and AND-combined:\n"
        "- `subject_id` — exact match on JWT `sub` claim\n"
        "- `outcome` — one of `allowed`, `denied`, `error`\n"
        "- `action` — exact policy action name (e.g. `write:hvac:setpoint`)\n"
        "- `resource_id` — normalized resource ID (e.g. `hvac:main`)\n"
        "- `limit` — max results returned (default 50, max 500)\n\n"
        "**Required action:** `read:audit:log` (admin role only)."
    ),
)
async def list_audit_events(
    subject_id:  Optional[str] = Query(default=None, description="Filter by JWT sub claim"),
    outcome:     Optional[str] = Query(default=None, description="Filter by outcome: allowed | denied | error"),
    action:      Optional[str] = Query(default=None, description="Filter by policy action name"),
    resource_id: Optional[str] = Query(default=None, description="Filter by normalized resource ID"),
    limit:       int           = Query(default=50, ge=1, le=500, description="Max results (1–500, default 50)"),
    _subject: Subject = Depends(require_action(actions.READ_AUDIT_LOG)),
) -> dict:
    # Validate outcome value if provided
    if outcome is not None and outcome not in ("allowed", "denied", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid outcome '{outcome}'. Valid values: allowed, denied, error",
        )

    events = await sqlite_store.query(
        subject_id=subject_id,
        outcome=outcome,
        action=action,
        resource_id=resource_id,
        limit=limit,
    )

    return {
        "events": events,
        "count":  len(events),
        "limit":  limit,
        "filter": {
            k: v for k, v in {
                "subject_id":  subject_id,
                "outcome":     outcome,
                "action":      action,
                "resource_id": resource_id,
            }.items() if v is not None
        },
    }


# ── Get single audit event ────────────────────────────────────────────────────

@router.get(
    "/{event_id}",
    summary="Get a single audit event",
    description=(
        "Returns a single audit event by its UUID `event_id`.\n\n"
        "**Required action:** `read:audit:log` (admin role only)."
    ),
)
async def get_audit_event(
    event_id: str,
    _subject: Subject = Depends(require_action(actions.READ_AUDIT_LOG)),
) -> dict:
    event = await sqlite_store.get_by_id(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit event '{event_id}' not found.",
        )
    return event
