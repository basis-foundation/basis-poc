# audit — module-level singleton, matches the ws_manager.py / broadcaster pattern.
#
# Import this anywhere audit logging is needed:
#   from audit import audit_logger
#
# To swap backends (e.g., for testing or when adding SQLite in Stage 5b),
# replace StdoutAuditStore() here — no call site changes required.

from audit.logger import AuditLogger
from audit.store import StdoutAuditStore

audit_logger = AuditLogger(store=StdoutAuditStore())
