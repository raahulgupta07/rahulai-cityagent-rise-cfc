"""
Job registry for pipeline runs — P2 (SQLite-backed, see deps/db.py).

Makes every stage run first-class: who ran, when, with what params, how it ended.
An in-memory dict holds live status; a SQLite mirror (`pipeline_jobs`) makes history
durable across restarts. Both are best-effort — a DB failure degrades to in-memory only,
never crashes a request.

A single non-reentrant lock (`try_acquire_heavy`) guarantees at most ONE heavy run
(extract / train / backtest / retrain — minutes long) at a time, so two clicks can't
launch two trainings that fight for CPU. Light stages are not gated.

IMPORTANT: the heavy lock is an in-process threading.Lock, so it only holds within a
single worker. Production MUST run one uvicorn worker (WEB_CONCURRENCY=1). Multi-worker
would need a shared lock (Redis / SQLite BEGIN IMMEDIATE row) instead.
"""
from __future__ import annotations
import json, logging, threading, uuid
from datetime import datetime, timezone

from .db import connect

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id         TEXT PRIMARY KEY,
    stage      TEXT,
    params     TEXT,
    heavy      INTEGER,
    mode       TEXT,
    status     TEXT,
    exit_code  INTEGER,
    error      TEXT,
    started    TEXT,
    finished   TEXT
);
"""

# ── in-memory store (live status) ───────────────────────────────────────────
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# ── heavy-run mutex (one at a time, in-process) ─────────────────────────────
_heavy_lock = threading.Lock()


def try_acquire_heavy() -> bool:
    """Non-blocking. True if this caller now owns the heavy-run slot."""
    return _heavy_lock.acquire(blocking=False)


def release_heavy() -> None:
    try:
        _heavy_lock.release()
    except RuntimeError:
        pass  # already released / not held


# ── full-experiment mutex (one whole chain at a time) ───────────────────────
# Distinct from the heavy lock: a full experiment runs several heavy stages in
# sequence, each grabbing/releasing _heavy_lock in turn. This coarser lock stops
# a SECOND full run from interleaving (and aborting mid-stage on the heavy lock).
_experiment_lock = threading.Lock()


def try_acquire_experiment() -> bool:
    """Non-blocking. True if this caller now owns the whole-experiment slot."""
    return _experiment_lock.acquire(blocking=False)


def release_experiment() -> None:
    try:
        _experiment_lock.release()
    except RuntimeError:
        pass


# ── SQLite mirror (best-effort) ─────────────────────────────────────────────
def _sql(query: str, params: tuple) -> None:
    try:
        conn = connect()
        conn.execute(_DDL)
        conn.execute(query, params)
        conn.commit()
        conn.close()
    except Exception as exc:  # DB locked/unwritable → in-memory stays authoritative
        log.debug("pipeline_jobs mirror skipped: %s", exc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── lifecycle ───────────────────────────────────────────────────────────────
def new_job(stage: str, params: dict | None, heavy: bool, mode: str) -> dict:
    jid = uuid.uuid4().hex[:12]
    rec = {
        "id": jid, "stage": stage, "params": params or {}, "heavy": heavy,
        "mode": mode, "status": "running", "exit_code": None, "error": None,
        "started": _now(), "finished": None,
    }
    with _jobs_lock:
        _jobs[jid] = rec
    _sql(
        "INSERT INTO pipeline_jobs (id,stage,params,heavy,mode,status,started) "
        "VALUES (?,?,?,?,?,?,?)",
        (jid, stage, json.dumps(params or {}), int(heavy), mode, "running", rec["started"]),
    )
    return rec


def finish_job(jid: str, exit_code: int | None, error: str | None = None) -> None:
    status = "done" if exit_code == 0 else "error"
    fin = _now()
    with _jobs_lock:
        rec = _jobs.get(jid)
        if rec:
            rec.update(status=status, exit_code=exit_code, error=error, finished=fin)
    _sql(
        "UPDATE pipeline_jobs SET status=?, exit_code=?, error=?, finished=? WHERE id=?",
        (status, exit_code, error, fin, jid),
    )


def get_job(jid: str) -> dict | None:
    with _jobs_lock:
        rec = _jobs.get(jid)
        return dict(rec) if rec else None


def list_jobs(limit: int = 50) -> list[dict]:
    """Live jobs from memory merged over durable history from SQLite (newest first)."""
    with _jobs_lock:
        mem = {r["id"]: dict(r) for r in _jobs.values()}
    merged = dict(mem)
    try:
        conn = connect()
        conn.execute(_DDL)
        cur = conn.execute(
            "SELECT id,stage,params,heavy,mode,status,exit_code,error,started,finished "
            "FROM pipeline_jobs ORDER BY started DESC LIMIT ?",
            (limit,),
        )
        for r in cur.fetchall():
            d = dict(r)
            if d["id"] in merged:
                continue  # live copy wins
            d["heavy"] = bool(d["heavy"])
            try:
                d["params"] = json.loads(d["params"]) if d["params"] else {}
            except Exception:
                d["params"] = {}
            merged[d["id"]] = d
        conn.close()
    except Exception as exc:
        log.debug("list_jobs history read skipped: %s", exc)
    rows = sorted(merged.values(), key=lambda r: r["started"], reverse=True)
    return rows[:limit]
