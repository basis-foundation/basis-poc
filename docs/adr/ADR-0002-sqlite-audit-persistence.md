# ADR-0002 — SQLite Audit Persistence

**Status:** Accepted  
**Date:** 2025-06-01  

## Context

Stage 5 introduced structured audit logging to stdout via `StdoutAuditStore`. This provided immediate operational visibility — `docker compose logs api | grep AUDIT` — but no persistence. Audit records were lost when the container restarted, and there was no way to query historical events without external log aggregation infrastructure.

Stage 5b required adding durable audit persistence. Several approaches were considered:

**PostgreSQL** — the conventional choice for relational persistence in a Docker Compose stack. Adding PostgreSQL would mean: a new service in the compose file, connection pooling, schema migration tooling, and a second stateful process to operate and back up. The audit table has a simple, flat schema that does not benefit from PostgreSQL's capabilities (foreign keys, joins, full-text search, replication). The operational cost is disproportionate to the problem.

**Elasticsearch or OpenSearch** — appropriate for log aggregation at scale, with full-text search and time-series analysis. Requires significant memory (2–4 GB minimum), a dedicated cluster for high availability, and operational expertise to manage. This is infrastructure suited to an organization running a SIEM, not a local OT control plane.

**External log aggregation (Loki, Splunk, etc.)** — introduces a network dependency on the audit write path, which violates the local-first and air-gap constraints. Audit writes must succeed even when the network is unavailable.

**SQLite** — a self-contained database engine in the Python standard library. The database is a single file on the local filesystem. No separate process, no network connection, no migration tooling beyond `CREATE TABLE IF NOT EXISTS`. Writes are synchronous to disk (WAL mode for concurrent access). The file can be inspected with any SQLite client, copied as a backup, or transported to an analyst's workstation.

## Decision

Audit events are persisted to a local SQLite database (`/data/audit.db`) via `SqliteAuditStore`. The database file lives in a named Docker volume (`audit_data`) mounted at `/data` in the API container.

The implementation uses the `sqlite3` standard library module exclusively — no SQLAlchemy, no migration framework, no ORM. The schema is defined as a single `CREATE TABLE IF NOT EXISTS` statement with five indices covering the common query dimensions. Writes are executed in a thread pool via `asyncio.to_thread()` to avoid blocking the event loop.

Stdout logging is preserved in full via `DualAuditStore`, which writes to both `StdoutAuditStore` and `SqliteAuditStore` in sequence. The two outputs serve different purposes: stdout provides real-time operational visibility; SQLite provides durable queryable history. Neither replaces the other.

The `GET /api/audit` endpoint exposes the persisted audit trail with AND-combined filters on `subject_id`, `outcome`, `action`, and `resource_id`. Results are ordered newest-first. Access is restricted to `admin` role.

## Consequences

**Accepted trade-offs:**
- SQLite is not appropriate for multi-writer deployments across separate hosts. If BASIS is eventually deployed as a horizontally scaled cluster, the audit store would need to be replaced with a network-accessible database. That replacement is a single class (`SqliteAuditStore`) behind a stable interface (`AuditStore`), not a cross-cutting refactor.
- SQLite does not support full-text search or complex time-series aggregation natively. Advanced audit analytics would require exporting the database or adding a reporting layer.

**Benefits realized:**
- Zero additional infrastructure. The audit database requires no new services, no new ports, and no operational expertise beyond the existing Docker Compose workflow.
- Air-gap compatible. Audit writes have no network dependency. The system continues to record all authorization decisions and command dispatches regardless of external network availability.
- Easily inspectable: `docker compose exec api sqlite3 /data/audit.db "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT 20"`.
- Backup is a file copy. Restore is a file copy.
- Consistent with the local-first architecture philosophy established in [ADR-0006](ADR-0006-local-first-architecture.md).
