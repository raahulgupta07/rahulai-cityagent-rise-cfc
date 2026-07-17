"""
Workflow slice — a LIVE map of the end-to-end pipeline for the Workflow screen.

One call returns the current state of every node in the flow so the UI can render an
interactive diagram: the Fabric data source, the training lane, the daily auto lane,
the human approval gate, and the consumption surfaces — each annotated with real
numbers (champion, pending challenger, last drift verdict, last order plan, schedule).

Reads Fabric cfc_* tables when USE_FABRIC=1 (else best-effort/empty). Never raises.
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _acc(w) -> float | None:
    if w is None:
        return None
    try:
        return round((1 - float(w)) * 100, 1)
    except (TypeError, ValueError):
        return None


@router.get("/status")
def status():
    """Live state of each workflow node. Neutral numbers (accuracy %, not WMAPE names)."""
    from deps import fabric, fabric_jobs

    out: dict = {
        "fabric": fabric.enabled(),
        "source": {"table": "CFC_Sales_Trans", "grain": "outlet × SKU × day",
                   "manual": ["holidays", "weather", "promo", "econ"]},
        "champion": None, "challenger": None, "awaiting_approval": False,
        "last_run": None, "drift": None, "order_plan": None, "runs_total": 0,
        "schedule": None, "feature_top": [],
    }
    if not fabric.enabled():
        return out

    try:
        ch = fabric.q(f"SELECT TOP 1 version FROM {fabric.table('cfc_champion')} ORDER BY created DESC")
        champ_v = ch[0]["version"] if ch else None
        runs = fabric.q(f"SELECT version, wmape, promoted, created FROM {fabric.table('cfc_model_runs')} ORDER BY created DESC")
        out["runs_total"] = len(runs)
        if champ_v:
            cr = next((r for r in runs if r["version"] == champ_v), None)
            out["champion"] = {"version": champ_v,
                               "accuracy": _acc(cr["wmape"]) if cr else None,
                               "since": str(cr["created"]) if cr else None}
        # challenger = newest run that is NOT the champion
        cand = next((r for r in runs if r["version"] != champ_v), None)
        if cand:
            out["challenger"] = {"version": cand["version"], "accuracy": _acc(cand["wmape"]),
                                 "created": str(cand["created"]),
                                 "delta": (round(_acc(cand["wmape"]) - out["champion"]["accuracy"], 1)
                                           if out["champion"] and out["champion"]["accuracy"] is not None
                                           and _acc(cand["wmape"]) is not None else None)}
            out["awaiting_approval"] = True
        if runs:
            out["last_run"] = {"version": runs[0]["version"], "accuracy": _acc(runs[0]["wmape"]),
                               "at": str(runs[0]["created"]), "promoted": bool(runs[0]["promoted"])}
    except Exception:
        pass

    # Cold-Fabric fallback: if the champion query failed/empty, fall back to the LOCAL
    # champion.json — same fallback deploy/versions uses — so no screen ever diverges
    # (deploy showing local while workflow shows none) during a brief Fabric blip.
    if out["champion"] is None:
        try:
            import json, pathlib
            p = pathlib.Path(__file__).resolve().parent.parent.parent / "models" / "champion.json"
            if p.exists():
                lc = json.loads(p.read_text())
                out["champion"] = {"version": lc.get("version"),
                                   "accuracy": _acc(lc.get("wmape")),
                                   "since": lc.get("cutoff")}
        except Exception:
            pass

    try:
        d = fabric.q(f"SELECT TOP 1 ts, verdict, data_drift, accuracy_drift FROM {fabric.table('cfc_drift')} ORDER BY ts DESC")
        if d:
            out["drift"] = {"at": str(d[0]["ts"]), "verdict": d[0]["verdict"],
                            "data_drift": bool(d[0]["data_drift"]),
                            "accuracy_drift": bool(d[0]["accuracy_drift"])}
    except Exception:
        pass

    try:
        op = fabric.q(f"SELECT MAX(date) mx, COUNT(*) n FROM {fabric.table('cfc_order_plan')}")
        if op and op[0]["mx"] is not None:
            out["order_plan"] = {"date": str(op[0]["mx"])[:10], "rows": int(op[0]["n"])}
    except Exception:
        pass

    try:
        fi = fabric.q(f"SELECT TOP 5 feature, gain FROM {fabric.table('cfc_feature_importance')} "
                      f"WHERE version = (SELECT TOP 1 version FROM {fabric.table('cfc_feature_importance')} ORDER BY gain DESC) "
                      f"ORDER BY gain DESC")
        out["feature_top"] = [{"name": r["feature"], "gain": round(float(r["gain"]), 1)} for r in fi]
    except Exception:
        pass

    try:
        scheds = fabric_jobs.schedules()
        out["schedule"] = scheds[0] if scheds else None
    except Exception:
        pass

    return out
