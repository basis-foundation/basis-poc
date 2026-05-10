"""
BASIS — AuditLogger
Thin facade over an AuditStore backend.

Call sites use this class exclusively — they never import AuditStore directly.
This means the backend can be swapped (stdout → SQLite → external SIEM) by
changing one line in audit/__init__.py, with zero changes to call sites.

Usage at a call site:
    from audit import audit_logger
    from domain.events import AuditEvent

    await audit_logger.record(AuditEvent(
        subject_id=...,
        subject_name=...,
        subject_roles=...,
        action="api_access",
        endpoint="GET /api/operator",
        outcome="allowed",
    ))

The record() method swallows all exceptions — audit failures must never
interrupt request processing.
"""

import logging

from audit.store import AuditStore, StdoutAuditStore
from domain.events import AuditEvent

log = logging.getLogger("basis.audit")


class AuditLogger:
    def __init__(self, store: AuditStore | None = None) -> None:
        self._store: AuditStore = store or StdoutAuditStore()

    async def record(self, event: AuditEvent) -> None:
        """
        Write one audit event via the configured store.

        Never raises. Any exception from the store backend is caught,
        logged as an error, and swallowed. Audit failures must not
        affect the outcome of the request being audited.
        """
        try:
            await self._store.write(event)
        except Exception as exc:
            log.error(
                "Audit write failed (non-fatal) — event_id=%s  error=%s",
                event.event_id, exc,
            )
