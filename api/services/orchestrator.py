"""
Agentic Autopilot orchestrator — P4.

The "machine": plans an end-to-end experiment, runs each stage as a tool (reusing the
P2 runner + job store + heavy-lock), interprets the outcome, and decides promote/hold.
It ORCHESTRATES the existing engine — it never re-implements any ML.

Autonomy dial:
    manual     — plan only, run nothing (dry preview of the plan)
    assisted   — run through training + gate, then STOP for the user's OK (default)
    full_auto  — also run predict + order after a successful gate

Narration + interpretation come from OpenRouter (services/llm) when a key is present;
otherwise deterministic templates are used, so Autopilot works offline.

Streaming: run() is an async generator of SSE-ready `data: {json}\n\n` lines. Event
`type` is one of: plan | step_start | log | step_done | interpret | decision |
awaiting_approval | done | error.
"""
from __future__ import annotations
import json
import pathlib
from typing import AsyncIterator

from services.runner import stream_stage, _STAGE_BY_ID
from services import llm

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHAMP = ROOT / "models" / "champion.json"
EVAL = ROOT / "reports" / "eval.md"

# Plan up to the gate (assisted stops here); tail runs only in full_auto.
_PLAN_TO_GATE = ["features", "retrain"]
_PLAN_TAIL = ["predict", "order"]

_STEP_BLURB = {
    "features": "Build the input signals (lags, trends, calendar, weather).",
    "retrain":  "Train a fresh candidate and gate it against the live model.",
    "predict":  "Generate the order plan from the live model.",
    "order":    "Roll the forecast into a warehouse make-list.",
}


def _sse(event: dict) -> str:
    # EventSourceResponse wraps this as the SSE `data:` field — do NOT prefix it here.
    return json.dumps(event)


def _plan_steps(autonomy: str) -> list[str]:
    steps = list(_PLAN_TO_GATE)
    if autonomy == "full_auto":
        steps += _PLAN_TAIL
    return steps


def _champion_wmape() -> float | None:
    if CHAMP.exists():
        try:
            return json.loads(CHAMP.read_text()).get("wmape")
        except Exception:
            return None
    return None


def _intro(autonomy: str, steps: list[str]) -> str:
    sys = "You are an ML forecasting agent. Be concise, plain-language, no jargon or method names."
    usr = (f"Explain in 2 sentences what you're about to do, running these steps for a bakery demand "
           f"forecast in {autonomy} mode: {', '.join(steps)}.")
    return llm.chat(sys, usr) or (
        f"Planning a {autonomy.replace('_', '-')} run: I'll {' then '.join(_STEP_BLURB[s].lower().rstrip('.') for s in steps)}. "
        f"I'll stop for your OK at the promote gate." if autonomy != "full_auto"
        else f"Running full-auto: {', '.join(steps)}. I'll promote the new model only if it beats the live one.")


def _interpret(before: float | None, after: float | None, promoted: bool) -> str:
    fb = "unknown" if before is None else f"{(1 - before) * 100:.1f}% accuracy"
    fa = "unknown" if after is None else f"{(1 - after) * 100:.1f}% accuracy"
    verdict = "promoted the new model — it beat the live one" if promoted else \
              "kept the live model — the candidate did not beat it"
    sys = "You are an ML forecasting agent. One short plain-language sentence, no jargon."
    usr = f"Live model was {fb}, candidate is {fa}. Decision: {verdict}. Summarise for a non-technical manager."
    return llm.chat(sys, usr) or f"Live model {fb}, candidate {fa} — {verdict}."


async def run(autonomy: str = "assisted", guard: bool = False,
              params: dict | None = None) -> AsyncIterator[str]:
    if autonomy not in ("manual", "assisted", "full_auto"):
        yield _sse({"type": "error", "message": f"bad autonomy: {autonomy}"})
        return

    steps = _plan_steps(autonomy)
    yield _sse({
        "type": "plan",
        "autonomy": autonomy,
        "narration": _intro(autonomy, steps),
        "steps": [{"id": s, "label": _STAGE_BY_ID[s]["label"], "blurb": _STEP_BLURB[s]} for s in steps],
    })

    if autonomy == "manual":
        yield _sse({"type": "awaiting_approval", "reason": "manual mode — review the plan, then run assisted or full-auto."})
        yield _sse({"type": "done"})
        return

    before = _champion_wmape()
    retrain_out: list[str] = []

    for sid in steps:
        yield _sse({"type": "step_start", "id": sid, "label": _STAGE_BY_ID[sid]["label"]})
        # safe demo (guard=True) simulates EVERY stage so the run is instant;
        # guard=False runs each stage for real (unbuffered → live logs).
        async for chunk in stream_stage(sid, guard_run=False, params=params, force_dry=guard):
            line = chunk.removeprefix("data: ").strip()
            if not line:
                continue
            if sid == "retrain":
                retrain_out.append(line)
            status = "error" if line.startswith("[ERROR]") else None
            if line.startswith("[DONE]"):
                yield _sse({"type": "step_done", "id": sid, "status": "done"})
            elif status:
                yield _sse({"type": "step_done", "id": sid, "status": "error", "line": line})
            else:
                yield _sse({"type": "log", "id": sid, "line": line})

        # After the gate step, interpret + decide.
        if sid == "retrain":
            joined = " ".join(retrain_out).lower()
            promoted = "promoted" in joined and "kept champion" not in joined
            after = _champion_wmape()
            yield _sse({"type": "interpret", "text": _interpret(before, after, promoted)})
            yield _sse({
                "type": "decision",
                "verdict": "promote" if promoted else "hold",
                "champion_accuracy": None if after is None else round((1 - after) * 100, 1),
                "detail": "New model is live." if promoted else "Live model unchanged.",
            })
            if autonomy == "assisted":
                yield _sse({"type": "awaiting_approval",
                            "reason": "Gate reached. Approve to generate the order plan, or stop here."})
                yield _sse({"type": "done"})
                return

    yield _sse({"type": "done"})
