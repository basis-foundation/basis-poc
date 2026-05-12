"""
BASIS — Audit Store
Stage 5:  StdoutAuditStore — writes structured audit lines to the uvicorn logger.
Stage 7:  action column widened; action names are now semantic policy strings.
Stage 8:  resource_type (rtype=) added as a first-class log field alongside resource=.
Stage 5b: SqliteAuditStore and DualAuditStore added.

Why SQLite
──────────
SQLite is the right persistence backend for a local-first OT security platform:
  - Zero infrastructure: no separate database server, no network dependency
  - Air-gap friendly: the DB is a single file on the container's local filesystem
  - Inspectable: `sqlite3 /data/audit.db "SELECT * FROM audit_events"` from any shell
  - Durable: persisted across container restarts via Docker named volume
  - Standard library: sqlite3 ships with Python — no extra dependencies, no CVEs
  - Sufficient: for a PoC / small-scale deployment, SQLite handles thousands of
    audit events per second without contention
  - Operationally simple: backup is `cp audit.db audit.db.bak`

Why stdout logging is still preserved (DualAuditStore)
──────────────────────────────────────────────────────
Stdout audit logs are grep-friendly in `docker compose logs` and are
immediately visible without any query tooling. They are the first line of
operational visibility during development and debugging. SQLite persistence
adds durable queryability on top — it does not replace the real-time
operational log stream. Both outputs serve different audiences:
  - stdout → developer watching live logs / grep recipes
  - SQLite → API consumer / audit reviewer querying history

The stdout format is designed to be grep-friendly in docker compose logs:

  AUDIT  outcome=allowed  subject=bob    action=read:api:operator             endpoint=GET /api/operator
  AUDIT  outcome=denied   subject=alice  action=read:api:operator             endpoint=GET /api/operator
  AUDIT  outcome=allowed  subject=bob    action=write:hvac:setpoint           endpoint=POST /api/controls/hvac/main/setpoint
  AUDIT  outcome=allowed  subject=bob    action=command_dispatch              resource=hvac:main  rtype=hvac
  AUDIT  outcome=error    subject=bob    action=command_dispatch              resource=hvac:main  rtype=hvac  reason=...

Grep recipes:
  All HVAC events:         docker compose logs api | grep "rtype=hvac"
  All denied decisions:    docker compose logs api | grep "AUDIT.*outcome=denied"
  Bob's audit trail:       docker compose logs api | grep "AUDIT.*subject=bob"
  All command dispatches:  docker compose logs api | grep "action=command_dispatch"
"""

import asyncio
import json
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional

from domain.events import AuditEvent

log = logging.getLogger("basis.audit")

# ── SQLite schema ─────────────────────────────────────────────────────────────
#
# One row per AuditEvent. All fields from the canonical AuditEvent model are
# stored explicitly — no JSON blob for top-level fields. detail is stored as
# a JSON string since it is an arbitrary dict.
#
# subject_roles is stored as a JSON array string for simplicity; it is
# reconstructed on read via json.loads().
#
# Indices cover the most common filter dimensions in GET /api/audit:
#   - timestamp DESC  (default ordering, most recent first)
#   - subject_id      (per-user audit trail)
#   - outcome         (show all denied / error events)
#   - action          (filter by policy action name)
#   - resource_id     (per-resource history)
#
_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id      TEXT    PRIMARY KEY,
    timestamp     TEXT    NOT NULL,
    subject_id    TEXT    NOT NULL,
    subject_name  TEXT    NOT NULL,
    subject_type  TEXT    NOT NULL DEFAULT 'human',
    subject_roles TEXT    NOT NULL DEFAULT '[]',
    action        TEXT    NOT NULL,
    resource_id   TEXT,
    resource_type TEXT,
    endpoint      TEXT,
    outcome       TEXT    NOT NULL,
    reason        TEXT,
    detail        TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp   ON audit_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_subject_id  ON audit_events (subject_id);
CREATE INDEX IF NOT EXISTS idx_audit_outcome     ON audit_events (outcome);
CREATE INDEX IF NOT EXISTS idx_audit_action      ON audit_events (action);
CREATE INDEX IF NOT EXISTS idx_audit_resource_id ON audit_events (resource_id);
"""


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
        # subject_type is omitted when "human" (the common case) to keep lines short;
        # it is included for non-human subjects to make device/service actions visible.
        subject_label = (
            f"{event.subject_name}({event.subject_type})"
            if event.subject_type != "human"
            else event.subject_name
        )
        parts = [
            f"outcome={event.outcome:<7}",
            f"subject={subject_label:<12}",
            f"action={event.action:<28}",
        ]

        if event.resource_id:
            parts.append(f"resource={event.resource_id}")
        if event.resource_type:
            parts.append(f"rtype={event.resource_type}")

        if event.endpoint:
            parts.append(f"endpoint={event.endpoint}")

        if event.reason:
            # Truncate long reason strings to keep lines readable
            reason = event.reason if len(event.reason) <= 80 else event.reason[:77] + "..."
            parts.append(f"reason={reason!r}")

        if event.detail:
            parts.append(f"detail={json.dumps(event.detail, separators=(',', ':'))}")

        log.info("AUDIT  %s", "  ".join(parts))


# ── SqliteAuditStore ──────────────────────────────────────────────────────────

class SqliteAuditStore(AuditStore):
    """
    Stage 5b: persists each AuditEvent to a local SQLite database.

    Design decisions
    ────────────────
    - sqlite3 standard library only — no SQLAlchemy, no migration framework
    - DB file created automatically on first use (CREATE TABLE IF NOT EXISTS)
    - Writes are executed in a thread pool via asyncio.to_thread() to avoid
      blocking the event loop on disk I/O (same pattern as publish_command)
    - Read methods are also off-thread for consistency
    - Connection-per-operation: avoids cross-thread connection sharing issues.
      SQLite file-level locking handles concurrent writes safely on a single
      host, and audit write throughput is low.
    - check_same_thread=False is not needed because we never share a connection
      across threads — each call opens, uses, and closes its own connection.
    - journal_mode=WAL: allows concurrent reads during a write, important for
      the audit query API running alongside the audit write path.

    Initialization
    ──────────────
    initialize() must be called once at startup (from main.py). It creates
    the DB file and schema if they do not exist. It is safe to call repeatedly
    (all DDL uses IF NOT EXISTS).

    Failure handling
    ────────────────
    write() swallows all exceptions and logs them — audit failures must
    never interrupt request processing (same contract as StdoutAuditStore).
    Query methods propagate exceptions to callers (the router handles them).
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        log.info("SqliteAuditStore configured — db_path=%s", db_path)

    def initialize(self) -> None:
        """
        Create the DB file and schema if they do not already exist.
        Called synchronously from main.py startup — before any requests arrive.
        """
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            log.info("Created audit DB directory: %s", db_dir)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
            log.info(
                "Audit DB initialized — path=%s  tables=audit_events",
                self.db_path,
            )
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Open a WAL-mode connection. Each caller is responsible for closing it."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── Write ─────────────────────────────────────────────────────────────────

    async def write(self, event: AuditEvent) -> None:
        """Insert one AuditEvent row. Never raises — logs and swallows on error."""
        try:
            await asyncio.to_thread(self._write_sync, event)
        except Exception as exc:
            log.error(
                "SqliteAuditStore write failed (non-fatal) — event_id=%s  error=%s",
                event.event_id, exc,
            )

    def _write_sync(self, event: AuditEvent) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO audit_events (
                    event_id, timestamp, subject_id, subject_name,
                    subject_type, subject_roles, action,
                    resource_id, resource_type, endpoint,
                    outcome, reason, detail
                ) VALUES (
                    :event_id, :timestamp, :subject_id, :subject_name,
                    :subject_type, :subject_roles, :action,
                    :resource_id, :resource_type, :endpoint,
                    :outcome, :reason, :detail
                )
                """,
                {
                    "event_id":      event.event_id,
                    "timestamp":     event.timestamp.isoformat(),
                    "subject_id":    event.subject_id,
                    "subject_name":  event.subject_name,
                    "subject_type":  event.subject_type,
                    "subject_roles": json.dumps(event.subject_roles),
                    "action":        event.action,
                    "resource_id":   event.resource_id,
                    "resource_type": event.resource_type,
                    "endpoint":      event.endpoint,
                    "outcome":       event.outcome,
                    "reason":        event.reason,
                    "detail":        json.dumps(event.detail),
                },
            )
            conn.commit()
        finally:
            conn.close()

    # ── Query ─────────────────────────────────────────────────────────────────

    async def query(
        self,
        *,
        subject_id:  Optional[str] = None,
        outcome:     Optional[str] = None,
        action:      Optional[str] = None,
        resource_id: Optional[str] = None,
        limit:       int = 50,
    ) -> list[dict]:
        """
        Return audit events newest-first, with optional equality filters.

        Filters are AND-combined. limit is capped at 500 to protect the API
        from unbounded response sizes.
        """
        limit = min(limit, 500)
        return await asyncio.to_thread(
            self._query_sync,
            subject_id=subject_id,
            outcome=outcome,
            action=action,
            resource_id=resource_id,
            limit=limit,
        )

    def _query_sync(
        self,
        *,
        subject_id:  Optional[str],
        outcome:     Optional[str],
        action:      Optional[str],
        resource_id: Optional[str],
        limit:       int,
    ) -> list[dict]:
        clauses: list[str] = []
        params:  list      = []

        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if outcome is not None:
            clauses.append("outcome = ?")
            params.append(outcome)
        if action is not None:
            clauses.append("action = ?")
            params.append(action)
        if resource_id is not None:
            clauses.append("resource_id = ?")
            params.append(resource_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql   = f"SELECT * FROM audit_events {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            conn.close()

    async def get_by_id(self, event_id: str) -> Optional[dict]:
        """Return a single audit event by event_id, or None if not found."""
        return await asyncio.to_thread(self._get_by_id_sync, event_id)

    def _get_by_id_sync(self, event_id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM audit_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict, deserializing JSON fields."""
    d = dict(row)
    d["subject_roles"] = json.loads(d.get("subject_roles") or "[]")
    d["detail"]        = json.loads(d.get("detail") or "{}")
    return d


# ── DualAuditStore ────────────────────────────────────────────────────────────

class DualAuditStore(AuditStore):
    """
    Composite store that writes to two backends in sequence.

    Used in production to combine StdoutAuditStore (operational grep-ability)
    with SqliteAuditStore (durable queryable persistence). Each store's
    own error handling applies independently — a failure in the primary does
    not skip the secondary.
    """

    def __init__(self, primary: AuditStore, secondary: AuditStore) -> None:
        self._primary   = primary
        self._secondary = secondary

    async def write(self, event: AuditEvent) -> None:
        await self._primary.write(event)
        await self._secondary.write(event)
