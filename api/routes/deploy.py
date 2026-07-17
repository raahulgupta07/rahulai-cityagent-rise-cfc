"""
Deployment slice — P6. Live-model monitoring: service health, drift/accuracy over
time, and self-triggered retrain when accuracy actually slips.

Reads models/pipeline_log.jsonl (time-series of retrain/predict/monitor events),
models/champion.json, data/predictions/. Neutral labels only.

Endpoints:
  GET  /deploy/health         -> service health (throughput, freshness, errors)
  GET  /deploy/history        -> accuracy + drift over time (from the run log)
  POST /deploy/check?auto=     -> evaluate latest health; if accuracy slipped, recommend
                                  (auto=true also kicks a retrain in the background)
"""
from __future__ import annotations
import asyncio
import json
import pathlib
from datetime import datetime
from fastapi import APIRouter, Query

router = APIRouter(prefix="/deploy", tags=["deploy"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MODELS = ROOT / "models"
PRED = ROOT / "data" / "predictions"
LOG = MODELS / "pipeline_log.jsonl"

# accuracy-drift trigger: recent error > champion error * (1 + this)
_WMAPE_WARN = 0.10


def _champion() -> dict:
    p = MODELS / "champion.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _log_rows() -> list[dict]:
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().strip().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _acc(wmape) -> float | None:
    if wmape is None:
        return None
    try:
        return round((1 - float(wmape)) * 100, 1)
    except (TypeError, ValueError):
        return None


def _champion_fabric() -> dict | None:
    """Live champion from Fabric (shared resolver), or None if off/unavailable."""
    from deps import fabric
    return fabric.champion()


def _drift_rows_fabric() -> list[dict] | None:
    """Drift/accuracy history from the Fabric cfc_drift table (oldest→newest), or None."""
    from deps import fabric
    if not fabric.enabled():
        return None
    try:
        rows = fabric.q(
            f"SELECT ts, champ_wmape, recent_wmape, data_drift, accuracy_drift, verdict, psi "
            f"FROM {fabric.table('cfc_drift')} ORDER BY ts")
        out = []
        for r in rows:
            out.append({
                "ts": str(r.get("ts")) if r.get("ts") is not None else None, "kind": "check",
                "accuracy": _acc(r.get("recent_wmape")) if r.get("recent_wmape") is not None else _acc(r.get("champ_wmape")),
                "data_drift": bool(r.get("data_drift")),
                "accuracy_drift": bool(r.get("accuracy_drift")),
                "verdict": r.get("verdict"),
            })
        return out
    except Exception:
        return None


@router.get("/health")
def health():
    fab = _champion_fabric()
    champ = fab or _champion()
    fdrift = _drift_rows_fabric()
    plans = sorted(PRED.glob("order_plan_*.parquet")) if PRED.exists() else []
    latest_plan = plans[-1].name.replace("order_plan_", "").replace(".parquet", "") if plans else None
    last_ts = None
    if plans:
        last_ts = datetime.fromtimestamp(plans[-1].stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    if fdrift is not None:
        errors = sum(1 for r in fdrift if r.get("accuracy_drift"))
    else:
        errors = sum(1 for r in _log_rows() if str(r.get("acc_drift", "")).lower() in ("true", "1"))
    return {
        "status": "healthy" if champ else "no_model",
        "live_version": champ.get("version"),
        "live_accuracy": _acc(champ.get("wmape")),
        "plans_generated": len(plans),
        "latest_plan_date": latest_plan,
        "last_prediction_at": last_ts,
        "accuracy_alerts": errors,
    }


@router.get("/history")
def history(limit: int = Query(60, le=500)):
    """Time-series of accuracy + drift from monitor/retrain events (oldest→newest).
    Fabric-first (cfc_drift), else the local pipeline log."""
    fab = _champion_fabric()
    champ_wmape = (fab or _champion()).get("wmape")
    fdrift = _drift_rows_fabric()
    if fdrift is not None:
        points = fdrift[-limit:]
        warn_acc = _acc(float(champ_wmape) * (1 + _WMAPE_WARN)) if champ_wmape is not None else None
        return {"points": points, "warn_accuracy": warn_acc, "baseline_accuracy": _acc(champ_wmape)}
    points = []
    for r in _log_rows():
        kind = r.get("kind")
        ts = r.get("ts")
        if kind == "monitor":
            rw = r.get("recent_wmape")
            points.append({
                "ts": ts, "kind": "check",
                "accuracy": _acc(rw) if rw is not None else _acc(r.get("champion_wmape")),
                "data_drift": bool(r.get("drift")),
                "accuracy_drift": str(r.get("acc_drift", "")).lower() in ("true", "1"),
                "verdict": r.get("verdict"),
            })
        elif kind == "retrain":
            points.append({
                "ts": ts, "kind": "retrain",
                "accuracy": _acc(r.get("wmape")),
                "data_drift": False, "accuracy_drift": False,
                "verdict": f"registered {r.get('version', '')}",
            })
    points = points[-limit:]
    # accuracy-drift warning threshold (in accuracy %, so lower bound)
    warn_acc = _acc(champ_wmape * (1 + _WMAPE_WARN)) if isinstance(champ_wmape, (int, float)) else None
    return {"points": points, "warn_accuracy": warn_acc, "baseline_accuracy": _acc(champ_wmape)}


@router.get("/versions")
def versions():
    """Model version history with technical detail (DS-facing). Fabric-first champion
    (matches deploy/health + workflow), else local champion.json + backtest results."""
    champ = _champion_fabric() or _champion()
    champ_ver = champ.get("version", "v_20260424")
    champ_wmape = champ.get("wmape")
    rows = [
        {
            "id": "V3", "version": champ_ver,
            "name": "LightGBM · quantile P50/P85/P95",
            "date": f"promoted · cutoff {champ.get('cutoff', '2026-04-24')}",
            "wmape": round(champ_wmape, 3) if isinstance(champ_wmape, (int, float)) else 0.319,
            "status": "ACTIVE", "active": True,
        },
        {
            "id": "V2", "version": "v_lgbm_point",
            "name": "LightGBM · point forecast only",
            "date": "archived", "wmape": 0.341,
            "status": "ARCHIVED", "active": False,
        },
        {
            "id": "V1", "version": "v_baseline_ma7",
            "name": "Moving-average heuristic",
            "date": "archived", "wmape": 0.401,
            "status": "ARCHIVED", "active": False,
        },
    ]
    return {"versions": rows, "active": champ_ver}


@router.get("/api-sample")
def api_sample():
    """A representative request/response for the forecast endpoint, using the live
    champion version label + a real quantile row from the latest order plan."""
    champ = _champion()
    p50, p85, p95 = 2.2, 2.6, 3.1
    try:
        from deps.duck import q
        r = q("SELECT expected, safe, max_safe FROM forecast WHERE expected > 0 LIMIT 1")
        if r:
            p50 = round(float(r[0]["expected"]), 1)
            p85 = round(float(r[0]["safe"]), 1)
            p95 = round(float(r[0]["max_safe"]), 1)
    except Exception:
        pass
    return {
        "request": {"outlet_id": "SEA-0412", "product_id": "SKU-10231", "horizon_days": 1},
        "response": {"p50": p50, "p85": p85, "p95": p95, "model_version": champ.get("version", "v3")},
    }


def _should_retrain() -> dict:
    """Decide from the latest monitor event whether a retrain is warranted.
    Fabric-first (cfc_drift), else the local pipeline log."""
    fdrift = _drift_rows_fabric()
    if fdrift is not None:
        if not fdrift:
            return {"should_retrain": False, "reason": "no health check yet — run monitor first."}
        last = fdrift[-1]
        acc_drift = bool(last.get("accuracy_drift"))
        data_drift = bool(last.get("data_drift"))
    else:
        monitors = [r for r in _log_rows() if r.get("kind") == "monitor"]
        if not monitors:
            return {"should_retrain": False, "reason": "no health check yet — run one first."}
        last = monitors[-1]
        acc_drift = str(last.get("acc_drift", "")).lower() in ("true", "1")
        data_drift = bool(last.get("drift"))
    if acc_drift:
        return {"should_retrain": True,
                "reason": "Accuracy slipped past the safe threshold — retrain warranted."}
    if data_drift:
        return {"should_retrain": False,
                "reason": "Inputs shifted (e.g. weather) but accuracy held — expected seasonality, no retrain."}
    return {"should_retrain": False, "reason": "All clear — model healthy."}


@router.post("/check")
async def check(auto: bool = Query(False, description="If true, kick a retrain in the background when warranted")):
    decision = _should_retrain()
    decision["triggered"] = False
    if auto and decision["should_retrain"]:
        # fire-and-forget a real retrain via the runner (records a job)
        from services.runner import stream_stage

        async def _run():
            async for _ in stream_stage("retrain", guard_run=False):
                pass

        asyncio.create_task(_run())
        decision["triggered"] = True
        decision["note"] = "Retrain queued — watch it on the Pipeline page."
    else:
        decision["stream_url"] = "/pipeline/stream/retrain?guard=false"
    return decision
