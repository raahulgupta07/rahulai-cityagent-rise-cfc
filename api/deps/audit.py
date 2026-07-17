"""
Audit log (SQLite — see deps/db.py) — separate table from uploads_audit (deps/store.py).

Table: audit_log(id, actor, action, target, ts)
  actor  — who triggered (user:role or system)
  action — verb: upload, override, sync, schedule_run, login, promote, …
  target — what was affected: file key, outlet_id, stage name, version, …

API:
    record_event(actor, action, target) — fire-and-forget, silent on DB failure
    list_events(limit)                  — newest first, empty list on DB failure
    get_db_audit()                      — FastAPI dependency (connection or None)
"""
from __future__ import annotations
import logging
from typing import Iterator

from .db import connect

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    actor   TEXT NOT NULL DEFAULT 'system',
    action  TEXT NOT NULL,
    target  TEXT,
    ts      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect():
    conn = connect()
    conn.execute(_DDL)
    return conn


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db_audit() -> Iterator:
    """Yield a live audit connection; None if DB is unavailable."""
    conn = None
    try:
        conn = _connect()
        yield conn
    except Exception as exc:
        log.warning("audit DB unavailable (%s); audit skipped", exc)
        yield None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── standalone helpers ────────────────────────────────────────────────────────

def record_event(actor: str, action: str, target: str = "") -> None:
    """Insert one audit row. Silent on failure — never raise to caller."""
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO audit_log (actor, action, target) VALUES (?, ?, ?)",
            (actor, action, target),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.warning("record_event failed: %s", exc)


def list_events(limit: int = 100) -> list[dict]:
    """Return recent audit rows newest-first. Empty list if DB unavailable."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT id, actor, action, target, ts FROM audit_log "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        log.warning("list_events failed: %s", exc)
        return []
