"""
Fabric-first ML routing — ML runs on FABRIC, the app only orchestrates.

When USE_FABRIC=1 AND the notebook job trigger is configured (FABRIC_WORKSPACE_ID +
FABRIC_NOTEBOOK_ID + creds), every REAL run of an ML stage is routed to the Fabric
notebook (CFC_ML_Pipeline) instead of a local subprocess:

    app stage        notebook MODE
    extract/sync  ->  features   (notebook aggregates raw sales in place)
    features      ->  features
    train/retrain ->  train      (registers a CHALLENGER; human approves in the app)
    backtest      ->  backtest
    predict       ->  predict    (writes cfc_order_plan + pred-vs-actual tables)
    monitor       ->  monitor    (writes cfc_drift)

Why: in-container LightGBM training on the full panel OOMs small servers; Fabric runs
Spark+LightGBM next to the 19.6M-row Lakehouse data. The local subprocess lane remains
ONLY as a fallback when Fabric is not configured (dev boxes, offline demo).

After a successful Fabric run the app's local serving parquet is re-hydrated from the
fresh cfc_* tables and the DuckDB views + Overview snapshot are rebuilt, so every
screen shows the new numbers without a restart.
"""
from __future__ import annotations
import logging, os, pathlib, time
from typing import Iterator

log = logging.getLogger(__name__)
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# app stage id -> notebook MODE
MODES: dict[str, str] = {
    "extract":  "features",
    "sync":     "features",
    "features": "features",
    "train":    "train",
    "retrain":  "train",
    "backtest": "backtest",
    "predict":  "predict",
    "monitor":  "monitor",
}

# local serving parquet each MODE makes stale (dropped -> re-hydrated from cfc_*)
_REFRESH: dict[str, list[str]] = {
    "features": ["data/raw/demand_panel.parquet", "data/raw/dim_product.parquet",
                 "data/raw/dim_branch.parquet"],
    "backtest": ["data/predictions/backtest_preds.parquet"],
    "predict":  ["data/predictions/order_plan.parquet"],
    "train":    [],
    "monitor":  [],
}


def enabled() -> bool:
    """Fabric ML lane on: read layer flag + job trigger fully configured."""
    from deps import fabric_jobs
    return os.getenv("USE_FABRIC", "0") == "1" and fabric_jobs.configured()


def covers(stage_id: str) -> bool:
    """True if a REAL run of this stage should go to Fabric instead of a subprocess."""
    return stage_id in MODES and enabled()


def _params_for(stage_id: str, params: dict | None) -> dict:
    """Map app stage params to the notebook's parameter-cell names."""
    src = params or {}
    p: dict = {}
    if src.get("cutoff"):
        p["CUTOFF"] = src["cutoff"]
    if src.get("date"):
        p["PREDICT_DATE"] = src["date"]
    return p


def iter_run(stage_id: str, params: dict | None = None,
             poll_s: int = 10, timeout_s: int = 3600) -> Iterator[str]:
    """BLOCKING generator of human-readable log lines: trigger the notebook, poll to
    completion, refresh local serving data. Never raises — the last line is
    [DONE] on success or [ERROR] on any failure (matches the runner's line protocol)."""
    from deps import fabric_jobs
    mode = MODES[stage_id]
    try:
        job = fabric_jobs.run(mode, _params_for(stage_id, params))
    except Exception as exc:
        yield f"[ERROR] Fabric job start failed: {exc}"
        return
    yield (f"[START] Fabric notebook MODE={mode} (job {job['job_id']}) — "
           f"running in the Fabric workspace, next to the data")
    yield "Heavy ML executes on Fabric Spark — this server only orchestrates and polls."

    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout_s:
        time.sleep(poll_s)
        try:
            st = fabric_jobs.status(job["job_id"])
        except Exception as exc:
            yield f"status poll failed ({exc}) — retrying"
            continue
        s = st.get("status") or "Unknown"
        if s != last:
            yield f"status: {s}"
            last = s
        else:
            yield f"… {s} — {int(time.time() - t0)}s elapsed"
        if s == "Completed":
            yield from _refresh(mode)
            yield "[DONE] Fabric run completed."
            return
        if s in ("Failed", "Cancelled", "Deduped"):
            yield f"[ERROR] Fabric job {s}: {st.get('failure') or 'see the Fabric run history'}"
            return
    yield (f"[ERROR] Timed out after {timeout_s}s — the Fabric job may still finish; "
           f"check the run history in Fabric.")


def _refresh(mode: str) -> Iterator[str]:
    """Drop stale local parquet, re-hydrate from the fresh cfc_* tables, rebuild views
    + Overview snapshot. Best-effort — a refresh failure never fails the run."""
    yield "refreshing local serving data from Fabric…"
    try:
        for rel in _REFRESH.get(mode, []):
            p = ROOT / rel
            if p.exists():
                p.unlink()
        from deps.hydrate import hydrate_from_fabric
        hydrate_from_fabric()
        from deps import duck, order_views
        duck.reset()
        order_views._registered = False
        yield "local data refreshed — screens now serve the new numbers."
    except Exception as exc:
        yield f"local refresh skipped: {exc}"
    try:
        import threading
        from routes import overview
        threading.Thread(target=overview._compute_and_cache, daemon=True).start()
        yield "overview snapshot rebuilding in the background."
    except Exception:
        pass
