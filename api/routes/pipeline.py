"""
Pipeline slice — 8-stage runner: status, kick, SSE live log.
Never exposes internal model names or ML jargon to the client.

Endpoints:
  GET  /pipeline/stages           — list all 8 stages with last-run / status
  POST /pipeline/run/{stage_id}   — kick a stage (dry-run by default for heavy stages)
  GET  /pipeline/stream/{stage_id} — SSE live log of a stage run
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from services.runner import stages_with_status, stream_stage, _STAGE_BY_ID
from deps import jobs as jobstore
from deps.auth import current_user


def _require_ops_for_live(guard: bool, user: dict) -> None:
    """Real (guard=false) runs train models / hit Fabric — ops/admin only. Dry-runs stay open."""
    if not guard and user["role"] not in ("ops", "admin"):
        raise HTTPException(403, "Live pipeline runs require the ops or admin role")

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _collect_params(cutoff: str | None, date: str | None, ref_cutoff: str | None) -> dict:
    """Build the whitelisted params dict from query args (runner filters per-stage)."""
    p: dict = {}
    if cutoff:     p["cutoff"] = cutoff
    if date:       p["date"] = date
    if ref_cutoff: p["ref-cutoff"] = ref_cutoff
    return p


@router.get("/stages")
def stages() -> list[dict]:
    """Return all 8 stages with last-run time and status inferred from output file mtimes."""
    return stages_with_status()


@router.get("/jobs")
def list_jobs(limit: int = Query(50, le=200)) -> list[dict]:
    """Run history — every real stage run with params, status, and timing."""
    return jobstore.list_jobs(limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    j = jobstore.get_job(job_id)
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(j)


@router.post("/run/{stage_id}")
async def run(
    stage_id: str,
    guard: bool = Query(True, description="If true, heavy stages dry-run only"),
    cutoff: str | None = Query(None, description="train: window split date YYYY-MM-DD"),
    date: str | None = Query(None, description="predict: target date YYYY-MM-DD"),
    ref_cutoff: str | None = Query(None, description="monitor: reference cutoff"),
    user: dict = Depends(current_user),
) -> JSONResponse:
    """Kick a stage. Returns immediately; stream output via GET /pipeline/stream/{stage_id}."""
    _require_ops_for_live(guard, user)
    if stage_id not in _STAGE_BY_ID:
        return JSONResponse({"error": f"Unknown stage: {stage_id}"}, status_code=404)
    stage = _STAGE_BY_ID[stage_id]
    is_dry = guard and stage["heavy"]
    qs = f"guard={str(guard).lower()}"
    for k, v in (("cutoff", cutoff), ("date", date), ("ref_cutoff", ref_cutoff)):
        if v:
            qs += f"&{k}={v}"
    return JSONResponse({
        "stage_id": stage_id,
        "label": stage["label"],
        "mode": "dry-run" if is_dry else "live",
        "stream_url": f"/pipeline/stream/{stage_id}?{qs}",
    })


@router.get("/stream/{stage_id}")
async def stream(
    stage_id: str,
    guard: bool = Query(True),
    cutoff: str | None = Query(None),
    date: str | None = Query(None),
    ref_cutoff: str | None = Query(None),
    user: dict = Depends(current_user),
):
    """SSE endpoint — streams stdout lines from a stage as text/event-stream."""
    _require_ops_for_live(guard, user)
    params = _collect_params(cutoff, date, ref_cutoff)

    async def generator():
        async for chunk in stream_stage(stage_id, guard_run=guard, params=params):
            yield chunk

    return EventSourceResponse(generator())
