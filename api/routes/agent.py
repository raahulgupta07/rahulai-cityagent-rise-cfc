"""
Agent slice — P4 Autopilot. Plan + run the whole experiment agentically.

Endpoints:
  GET  /agent/status              -> LLM narration on/off, model, autonomy options
  GET  /agent/plan?autonomy=      -> the step plan (no execution)
  GET  /agent/run?autonomy=&guard= -> SSE stream: plan -> steps -> interpret -> decision
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from services import orchestrator, llm
from services.runner import _STAGE_BY_ID
from deps.auth import current_user

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
def status():
    return {
        "llm_narration": llm.enabled(),
        "model": llm.model() if llm.enabled() else None,
        "autonomy_options": ["manual", "assisted", "full_auto"],
        "default_autonomy": "assisted",
    }


@router.get("/plan")
def plan(autonomy: str = Query("assisted")):
    steps = orchestrator._plan_steps(autonomy)
    return {
        "autonomy": autonomy,
        "narration": orchestrator._intro(autonomy, steps),
        "steps": [{"id": s, "label": _STAGE_BY_ID[s]["label"], "blurb": orchestrator._STEP_BLURB[s]} for s in steps],
    }


@router.get("/run")
async def run(
    autonomy: str = Query("assisted"),
    guard: bool = Query(True, description="If true, heavy stages dry-run (safe demo). "
                                          "guard=false runs the REAL pipeline — ops/admin only."),
    cutoff: str | None = Query(None),
    user: dict = Depends(current_user),
):
    # SAFE DEFAULT: guard now defaults to True (dry-run). A real run (guard=false) trains
    # models + spends LLM tokens — restrict to ops/admin. (Previously guard defaulted to
    # False, so a plain GET kicked a ~12-min real pipeline run.)
    if not guard and user["role"] not in ("ops", "admin"):
        raise HTTPException(403, "Live agent runs require the ops or admin role")
    params = {"cutoff": cutoff} if cutoff else None

    async def gen():
        async for chunk in orchestrator.run(autonomy=autonomy, guard=guard, params=params):
            yield chunk

    return EventSourceResponse(gen())
