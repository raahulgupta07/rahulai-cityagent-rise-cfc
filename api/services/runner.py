"""
Pipeline stage runner — wraps subprocess calls to src/<script>.py and streams stdout.

Stage → script mapping lives here; the route layer only knows stage names.
For heavy stages (extract, train) the run is GUARDED: call guard_run=True (default)
to get a dry-echo so the frontend SSE is wired and tested without triggering a
5-minute training job. Pass guard_run=False for real execution (future admin flag).
"""
from __future__ import annotations
import asyncio
import pathlib
import sys
from datetime import datetime
from typing import AsyncIterator

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"

# ── stage definitions ────────────────────────────────────────────────────────

STAGES: list[dict] = [
    {
        "id": "extract",
        "label": "Data extraction",
        "description": "Pull daily sales from source system",
        "script": "extract.py",
        "args": [],
        "heavy": True,
        "output_files": ["data/raw/dim_branch.parquet", "data/raw/dim_product.parquet"],
    },
    {
        "id": "sync",
        "label": "Sync from database",
        "description": "Pull new sales since the last sync (incremental, monthly batches)",
        "script": "extract.py",
        "args": ["fact"],
        "heavy": True,
        "output_files": ["data/raw/demand_panel.parquet"],
    },
    {
        "id": "features",
        "label": "Feature engineering",
        "description": "Build lag, rolling, calendar, and weather features",
        "script": "features.py",
        "args": [],
        "heavy": False,
        "output_files": ["data/features/train.parquet"],
    },
    {
        "id": "baselines",
        "label": "Baseline models",
        "description": "Run simple reference methods (moving average, naive)",
        "script": "baselines.py",
        "args": [],
        "heavy": False,
        "output_files": ["reports/baselines.md"],
    },
    {
        "id": "train",
        "label": "Model training",
        "description": "Train forecasting model on historical data",
        "script": "train.py",
        "args": [],
        "heavy": True,
        "output_files": ["models/lgbm_p50.txt", "models/lgbm_p85.txt"],
    },
    {
        "id": "backtest",
        "label": "Backtest",
        "description": "Rolling-origin evaluation across 3 time periods",
        "script": "backtest.py",
        "args": [],
        "heavy": True,
        "output_files": ["reports/eval.md", "data/predictions/backtest_preds.parquet"],
    },
    {
        "id": "order",
        "label": "Order quantities",
        "description": "Convert forecasts to daily order plan per outlet",
        "script": "order_qty.py",
        "args": ["build"],
        "heavy": False,
        "output_files": ["data/predictions/order_plan.parquet", "reports/order_policy.md"],
    },
    {
        "id": "predict",
        "label": "Daily predictions",
        "description": "Generate tomorrow's order plan from live model",
        "script": "pipeline.py",
        "args": ["predict", "--date", datetime.today().strftime("%Y-%m-%d")],
        "heavy": False,
        "output_files": [],   # order_plan_<date>.parquet varies by date
    },
    {
        "id": "monitor",
        "label": "Health check",
        "description": "Check for input signal shifts and accuracy changes",
        "script": "pipeline.py",
        "args": ["monitor"],
        "heavy": False,
        "output_files": ["reports/drift_monitor.md"],
    },
    {
        "id": "retrain",
        "label": "Retrain experiment",
        "description": "Train a fresh candidate and register it; promote only if it beats the live model",
        "script": "pipeline.py",
        "args": ["retrain"],
        "heavy": True,
        "output_files": ["models/champion.json"],
    },
]

_STAGE_BY_ID: dict[str, dict] = {s["id"]: s for s in STAGES}


# ── output-file mtime → status ───────────────────────────────────────────────

def _stage_status(stage: dict) -> dict:
    """Infer last-run time and status from output file mtimes."""
    files = stage["output_files"]
    last_run: str | None = None
    status = "pending"

    for rel in files:
        p = ROOT / rel
        if p.exists():
            mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            if last_run is None or mt > last_run:
                last_run = mt
            status = "done"

    # predict: check for any order_plan_<date>.parquet
    if stage["id"] == "predict":
        pred_dir = ROOT / "data" / "predictions"
        if pred_dir.exists():
            dated = sorted(pred_dir.glob("order_plan_*.parquet"))
            if dated:
                mt = datetime.fromtimestamp(dated[-1].stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                last_run = mt
                status = "done"

    return {"last_run": last_run, "status": status}


def stages_with_status() -> list[dict]:
    result = []
    for s in STAGES:
        info = _stage_status(s)
        result.append({
            "id": s["id"],
            "label": s["label"],
            "description": s["description"],
            "heavy": s["heavy"],
            "status": info["status"],
            "last_run": info["last_run"],
        })
    return result


# ── async subprocess runner ───────────────────────────────────────────────────

# ── param → CLI arg mapping ──────────────────────────────────────────────────
# Whitelist of params each stage accepts, so the UI can re-run with settings.
_STAGE_PARAMS: dict[str, set[str]] = {
    "train":   {"cutoff"},          # src/train.py --cutoff YYYY-MM-DD (train window split)
    "retrain": {"cutoff"},          # pipeline.py retrain --cutoff (registers a version)
    "predict": {"date"},            # pipeline.py predict --date
    "monitor": {"ref-cutoff"},      # pipeline.py monitor --ref-cutoff
}


def _extra_args(stage_id: str, params: dict | None) -> list[str]:
    """Turn a whitelisted params dict into CLI flags. Unknown keys ignored."""
    if not params:
        return []
    allowed = _STAGE_PARAMS.get(stage_id, set())
    out: list[str] = []
    for k, v in params.items():
        if k in allowed and v not in (None, ""):
            out += [f"--{k}", str(v)]
    return out


async def stream_stage(
    stage_id: str,
    guard_run: bool = True,
    params: dict | None = None,
    force_dry: bool = False,
) -> AsyncIterator[str]:
    """
    Async generator that yields stdout lines from a stage subprocess.
    Dry-run (echo, no execution) when force_dry=True, OR when guard_run=True and the
    stage is heavy. force_dry lets the agent's "safe demo" simulate EVERY stage so it
    is instant. Real runs are unbuffered (-u) so stdout streams live, and heavy real
    runs acquire a global lock so only one runs at a time. Every real run records a job.
    """
    from deps import jobs

    stage = _STAGE_BY_ID.get(stage_id)
    if not stage:
        yield f"Unknown stage: {stage_id}"
        yield "[ERROR] unknown stage"
        return

    script = SRC / stage["script"]
    if not script.exists():
        yield f"Script not found: {script}"
        yield "[ERROR] script missing"
        return

    if force_dry or (guard_run and stage["heavy"]):
        yield f"[START] {stage['label']} (safe demo — simulated)"
        yield f"would build/run: {stage['description'].lower()}"
        yield "[DONE] simulated — turn off safe demo to run for real."
        return

    # Real run of a heavy stage → acquire the one-at-a-time slot.
    held_heavy = False
    if stage["heavy"]:
        if not jobs.try_acquire_heavy():
            yield f"[ERROR] Another heavy run is already in progress. Try again shortly."
            return
        held_heavy = True

    cmd = [sys.executable, "-u", str(script)] + stage["args"] + _extra_args(stage_id, params)
    job = jobs.new_job(stage_id, params, stage["heavy"], mode="live")
    rc: int | None = None
    err: str | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        assert proc.stdout is not None

        yield f"[START] {stage['label']} — {datetime.now().strftime('%H:%M:%S')} (job {job['id']})"

        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                yield f"{line}"

        await proc.wait()
        rc = proc.returncode
        if rc == 0:
            yield f"[DONE] Completed successfully."
        else:
            err = f"exit code {rc}"
            yield f"[ERROR] Process exited with code {rc}."

    except Exception as exc:
        err = str(exc)
        yield f"[ERROR] {exc}"
    finally:
        jobs.finish_job(job["id"], rc if rc is not None else -1, err)
        if held_heavy:
            jobs.release_heavy()
