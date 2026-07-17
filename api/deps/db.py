"""
SQLite operational store — single file `data/app.db`.

Replaces Postgres for the app's operational metadata (uploads_audit, audit_log,
pipeline_jobs, scheduler_state). Zero server, stdlib `sqlite3`, no external dependency.

Design:
- WAL journal + busy_timeout so the single uvicorn worker's concurrent request
  threads don't collide on writes.
- Every caller catches exceptions (same graceful pattern as before): a locked or
  unwritable DB degrades to a no-op / empty list, never crashes a request.
- Correct ONLY under a single process (WEB_CONCURRENCY=1). The heavy-run lock in
  deps/jobs.py is an in-process threading.Lock; multi-worker would need Redis/PG
  advisory locks instead. Prod compose pins one worker for this reason.

Env: APP_DB_PATH overrides the file location (prod mounts a volume at data/).
"""
from __future__ import annotations
import os, sqlite3, logging
from pathlib import Path

log = logging.getLogger(__name__)

# api/deps/db.py → parents[2] == repo root; data/ sits beside src/.
_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "app.db"
DB_PATH = os.getenv("APP_DB_PATH", str(_DEFAULT))


def connect() -> sqlite3.Connection:
    """Open a SQLite connection to the app store (WAL, row factory). Raises on failure."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
