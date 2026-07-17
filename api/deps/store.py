"""
Upload audit store (SQLite — see deps/db.py).

Gracefully handles a locked/unwritable DB: returns empty / logs rather than crashing.
Provides get_db() FastAPI dependency + record_audit / list_audits helpers.
"""
from __future__ import annotations
import logging
from typing import Iterator

from .db import connect

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS uploads_audit (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    key      TEXT,
    filename TEXT,
    rows     INTEGER,
    accepted INTEGER,
    ts       TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect():
    conn = connect()
    conn.execute(_DDL)
    return conn


# ── FastAPI dependency ──────────────────────────────────────────────────────

def get_db() -> Iterator:
    """Yield a live connection; close on exit. Yields None if DB unavailable."""
    conn = None
    try:
        conn = _connect()
        yield conn
    except Exception as exc:
        log.warning("DB unavailable (%s); upload audit skipped", exc)
        yield None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── standalone helpers (called from routes without DI) ─────────────────────

def record_audit(key: str, filename: str, rows: int, accepted: bool) -> None:
    """Insert one audit row. Silent on failure."""
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO uploads_audit (key, filename, rows, accepted) VALUES (?, ?, ?, ?)",
            (key, filename, rows, int(accepted)),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.warning("record_audit failed: %s", exc)


def list_audits() -> list[dict]:
    """Return all audit rows newest-first. Empty list if DB unavailable."""
    try:
        conn = _connect()
        cur = conn.execute(
            "SELECT id, key, filename, rows, accepted, ts FROM uploads_audit ORDER BY ts DESC, id DESC"
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        log.warning("list_audits failed: %s", exc)
        return []
