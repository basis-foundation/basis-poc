# audit — module-level singletons, matches the ws_manager.py / broadcaster pattern.
#
# Exports:
#   audit_logger  — AuditLogger singleton for writing audit events.
#                   Call sites: require_action(), routers/controls.py
#                   Use:  from audit import audit_logger
#
#   sqlite_store  — SqliteAuditStore singleton for querying persisted events.
#                   Call sites: routers/audit.py (GET /api/audit endpoints)
#                   Use:  from audit import sqlite_store
#
# Stage 5b: dual-write via DualAuditStore.
#   Primary:   StdoutAuditStore  — grep-friendly operational logs (unchanged)
#   Secondary: SqliteAuditStore  — durable local-first persistence (new)
#
# initialize_audit_db() must be called once at startup (main.py) to create
# the SQLite DB file and schema before the first request arrives.
#
# DB path: AUDIT_DB_PATH env var, default /data/audit.db
# This path is inside the Docker named volume audit_data mounted at /data.

import os

from audit.logger import AuditLogger
from audit.store  import DualAuditStore, SqliteAuditStore, StdoutAuditStore

_db_path     = os.getenv("AUDIT_DB_PATH", "/data/audit.db")
sqlite_store = SqliteAuditStore(_db_path)
audit_logger = AuditLogger(store=DualAuditStore(StdoutAuditStore(), sqlite_store))


def initialize_audit_db() -> None:
    """
    Create the SQLite DB file and schema if they do not already exist.
    Call once from main.py startup before any requests are processed.
    Safe to call repeatedly — all DDL uses IF NOT EXISTS.
    """
    sqlite_store.initialize()
