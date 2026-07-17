"""
Schedule routes — /schedule prefix.

GET  /schedule/status           → list of jobs with enabled, schedule, last_run, last_status
POST /schedule/toggle/{job_id}  → flip enabled flag (requires ops or admin)
POST /schedule/run-now/{job_id} → trigger immediately (requires admin; heavy guard still applies)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from deps.auth import require_role
from deps.audit import record_event
from services.scheduler import get_status, toggle_job, run_now

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/status")
def schedule_status():
    """Return all scheduled jobs and their current state."""
    return {"jobs": get_status()}


@router.post("/toggle/{job_id}")
def toggle(job_id: str, user: dict = Depends(require_role("ops", "admin"))):
    """Toggle enabled/disabled for a job. Ops and admin only."""
    try:
        updated = toggle_job(job_id)
    except KeyError:
        raise HTTPException(404, f"Unknown job: {job_id!r}")
    record_event(user["actor"], "schedule_toggle", f"{job_id}→{'on' if updated['enabled'] else 'off'}")
    return {"job": updated}


@router.post("/run-now/{job_id}")
def trigger_now(job_id: str, user: dict = Depends(require_role("admin"))):
    """Fire a job immediately (admin only). Returns immediately — job runs in background."""
    try:
        result = run_now(job_id)
    except KeyError:
        raise HTTPException(404, f"Unknown job: {job_id!r}")
    record_event(user["actor"], "schedule_run_now", job_id)
    return result
