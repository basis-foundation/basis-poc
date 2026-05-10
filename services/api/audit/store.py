"""
BASIS — Audit Store
Stage 5: StdoutAuditStore — writes structured audit lines to the uvicorn logger.

Stage 5b will add SqliteAuditStore. The interface is defined here so that
AuditLogger can swap backends without any change to call sites.

The stdout format is designed to be grep-friendly in docker compose logs:

  AUDIT outcome=allowed  subject=bob    action=api_access        endpoint=GET /api/operator
  AUDIT outcome=denied   subject=alice  action=api_access        endpoint=GET /api/operator
  AUDIT outcome=allowed  subject=bob    action=command_dispatch  resource=hvac:main
  AUDIT outcome=error    subject=bob    action=command_dispatch  resource=hvac:main  reason=...
"""

import json
import logging
from abc import ABC, abstractmethod

from domain.events import AuditEvent

log = logging.getLogger("basis.audit")


class AuditStore(ABC):
    """
    Abstract base for audit persistence backends.
    Implementations must be safe to call from async context.
    """

    @abstractmethod
    async def write(self, event: AuditEvent) -> None:
        """Persist one audit event. Must not raise — log and swallow on error."""
        ...


class StdoutAuditStore(AuditStore):
    """
    Stage 5 implementation: writes a structured single-line audit record to
    the basis.audit logger at INFO level.

    Behavior is identical to what the current implicit logging produces, but
    through a typed, consistent interface that Stage 5b can replace with SQLite.
    """

    async def write(self, event: AuditEvent) -> None:
        # Build a compact key=value line for easy grepping.
        # Pad field values so columns align in typical log viewers.
        parts = [
            f"outcome={event.outcome:<7}",
            f"subject={event.subject_name:<12}",
            f"action={event.action:<20}",
        ]

        if event.resource_id:
            parts.append(f"resource={event.resource_id}")

        if event.endpoint:
            parts.append(f"endpoint={event.endpoint}")

        if event.reason:
            # Truncate long reason strings to keep lines readable
            reason = event.reason if len(event.reason) <= 80 else event.reason[:77] + "..."
            parts.append(f"reason={reason!r}")

        if event.detail:
            parts.append(f"detail={json.dumps(event.detail, separators=(',', ':'))}")

        log.info("AUDIT  %s", "  ".join(parts))
