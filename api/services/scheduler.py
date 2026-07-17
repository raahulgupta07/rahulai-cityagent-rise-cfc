"""
Lightweight stdlib thread-based scheduler — zero new dependencies.

Jobs:
  - nightly_predict  : runs `python3 src/pipeline.py predict --date <today>`
                       at 00:30 local time every day.
  - weekly_retrain   : runs `python3 src/pipeline.py retrain`
                       at 01:00 every Monday.

SAFETY:
  Both jobs default to DISABLED (enabled=False). Toggle via POST /schedule/toggle/{job}.
  Even when enabled, each job has a guard that must be passed in code — there is no
  way for the scheduler to run a heavy job without `_JOBS[id]["enabled"] == True`.
  State is in-process memory; a restart resets to disabled. Persist toggle state to
  DB in a future iteration if needed (add to audit_log / a config table).

Wiring (add to main.py — SEE SUMMARY):
    from services.scheduler import start as start_scheduler, stop as stop_scheduler
    app.on_event("startup")(start_scheduler)
    app.on_event("shutdown")(stop_scheduler)
"""
from __future__ import annotations
import logging, pathlib, subprocess, sys, threading, time
from datetime import datetime

log = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SRC  = ROOT / "src"

# ── job registry ──────────────────────────────────────────────────────────────

_JOBS: dict[str, dict] = {
    "nightly_sync": {
        "id":          "nightly_sync",
        "label":       "Nightly data sync",
        "description": "Pull new sales from the database since the last sync (incremental)",
        "enabled":     False,
        "schedule":    "daily @ 00:05",
        "hour":        0,
        "minute":      5,
        "weekday":     None,
        "script":      "extract.py",
        "args":        ["fact"],
        "last_run":    None,
        "last_status": None,
    },
    "nightly_predict": {
        "id":          "nightly_predict",
        "label":       "Nightly predict",
        "description": "Generate tomorrow's order plan from the live champion model",
        "enabled":     False,
        "schedule":    "daily @ 00:30",
        "hour":        0,
        "minute":      30,
        "weekday":     None,          # None = every day
        "script":      "pipeline.py",
        "args":        ["predict"],   # --date appended at runtime
        "last_run":    None,
        "last_status": None,
    },
    "weekly_retrain": {
        "id":          "weekly_retrain",
        "label":       "Weekly retrain",
        "description": "Re-evaluate champion vs challenger; promote if WMAPE improves ≥1 %",
        "enabled":     False,
        "schedule":    "Monday @ 01:00",
        "hour":        1,
        "minute":      0,
        "weekday":     0,             # 0 = Monday
        "script":      "pipeline.py",
        "args":        ["retrain"],
        "last_run":    None,
        "last_status": None,
    },
}

_lock   = threading.Lock()
_thread: threading.Thread | None = None
_stop   = threading.Event()


# ── toggle persistence (survives restart; graceful if DB down) ──────────────────
from deps.db import connect as _db_connect
_STATE_DDL = "CREATE TABLE IF NOT EXISTS scheduler_state (job_id TEXT PRIMARY KEY, enabled INTEGER)"


def _persist_toggle(job_id: str, enabled: bool) -> None:
    try:
        conn = _db_connect()
        conn.execute(_STATE_DDL)
        conn.execute(
            "INSERT INTO scheduler_state (job_id, enabled) VALUES (?,?) "
            "ON CONFLICT (job_id) DO UPDATE SET enabled=excluded.enabled",
            (job_id, int(enabled)))
        conn.commit()
        conn.close()
    except Exception as exc:
        log.debug("scheduler_state persist skipped: %s", exc)


def _load_persisted() -> None:
    """On startup, restore enabled flags from DB (in-memory default = off)."""
    try:
        conn = _db_connect()
        conn.execute(_STATE_DDL)
        cur = conn.execute("SELECT job_id, enabled FROM scheduler_state")
        with _lock:
            for jid, enabled in cur.fetchall():
                if jid in _JOBS:
                    _JOBS[jid]["enabled"] = bool(enabled)
        conn.close()
        log.info("scheduler: restored toggle state from DB")
    except Exception as exc:
        log.debug("scheduler_state load skipped (defaults=off): %s", exc)


# ── scheduler loop ────────────────────────────────────────────────────────────

def _should_run(job: dict, now: datetime, last_fired: dict) -> bool:
    """True if the job is enabled and its scheduled time just passed (within the check window)."""
    if not job["enabled"]:
        return False
    if now.hour != job["hour"] or now.minute != job["minute"]:
        return False
    if job["weekday"] is not None and now.weekday() != job["weekday"]:
        return False
    # Avoid firing twice in the same minute
    key = f"{now.year}{now.month}{now.day}{now.hour}{now.minute}"
    if last_fired.get(job["id"]) == key:
        return False
    last_fired[job["id"]] = key
    return True


def _run_job(job: dict) -> None:
    """Spawn subprocess and update last_run/status. Blocking — called in background thread."""
    script = SRC / job["script"]
    extra_args = list(job["args"])
    if job["id"] == "nightly_predict":
        extra_args += ["--date", datetime.today().strftime("%Y-%m-%d")]

    cmd = [sys.executable, str(script)] + extra_args
    log.info("scheduler: starting job %s → %s", job["id"], " ".join(cmd))

    start = datetime.now()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        status = "ok" if result.returncode == 0 else f"error (rc={result.returncode})"
        if result.returncode != 0:
            log.warning("scheduler: job %s failed:\n%s", job["id"], result.stderr[-2000:])
        else:
            log.info("scheduler: job %s finished ok in %ss", job["id"], (datetime.now()-start).seconds)
    except Exception as exc:
        status = f"exception: {exc}"
        log.error("scheduler: job %s raised: %s", job["id"], exc)

    with _lock:
        job["last_run"]    = start.strftime("%Y-%m-%d %H:%M")
        job["last_status"] = status

    # Emit audit event (best-effort)
    try:
        from deps.audit import record_event
        record_event("system:scheduler", f"job_{status}", job["id"])
    except Exception:
        pass


def _loop() -> None:
    last_fired: dict[str, str] = {}
    log.info("scheduler: loop started")
    while not _stop.is_set():
        now = datetime.now()
        with _lock:
            jobs = list(_JOBS.values())
        for job in jobs:
            if _should_run(job, now, last_fired):
                t = threading.Thread(target=_run_job, args=(job,), daemon=True)
                t.start()
        _stop.wait(timeout=30)   # wake every 30 s, plenty fine for minute-resolution jobs
    log.info("scheduler: loop stopped")


# ── lifecycle (wired by main.py) ──────────────────────────────────────────────

def start() -> None:
    global _thread
    _load_persisted()          # restore enabled flags across restarts
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="cfc-scheduler")
    _thread.start()
    log.info("scheduler: started")


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
    log.info("scheduler: stopped")


# ── public API (used by routes/schedule.py) ───────────────────────────────────

def get_status() -> list[dict]:
    """Return a copy of all job status dicts (safe for JSON serialisation)."""
    with _lock:
        return [
            {
                "id":          j["id"],
                "label":       j["label"],
                "description": j["description"],
                "enabled":     j["enabled"],
                "schedule":    j["schedule"],
                "last_run":    j["last_run"],
                "last_status": j["last_status"],
            }
            for j in _JOBS.values()
        ]


def toggle_job(job_id: str) -> dict:
    """Flip enabled flag. Returns new status dict or raises KeyError."""
    with _lock:
        if job_id not in _JOBS:
            raise KeyError(job_id)
        _JOBS[job_id]["enabled"] = not _JOBS[job_id]["enabled"]
        new_state = _JOBS[job_id]["enabled"]
        snapshot = dict(_JOBS[job_id])
    _persist_toggle(job_id, new_state)   # survive restart
    return snapshot


def run_now(job_id: str) -> dict:
    """Trigger a job immediately in a background thread. Returns job dict."""
    with _lock:
        if job_id not in _JOBS:
            raise KeyError(job_id)
        job = _JOBS[job_id]

    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()
    return {"job_id": job_id, "queued": True}
