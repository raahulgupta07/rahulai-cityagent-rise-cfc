"""
Agent slice — P4 Autopilot. Plan + run the whole experiment agentically.

Endpoints:
  GET  /agent/status              -> LLM narration on/off, model, autonomy options
  GET  /agent/plan?autonomy=      -> the step plan (no execution)
  GET  /agent/run?autonomy=&guard= -> SSE stream: plan -> steps -> interpret -> decision
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from services import orchestrator, llm
from services.runner import _STAGE_BY_ID

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
    guard: bool = Query(False, description="If true, heavy stages dry-run (safe demo)"),
    cutoff: str | None = Query(None),
):
    params = {"cutoff": cutoff} if cutoff else None

    async def gen():
        async for chunk in orchestrator.run(autonomy=autonomy, guard=guard, params=params):
            yield chunk

    return EventSourceResponse(gen())
