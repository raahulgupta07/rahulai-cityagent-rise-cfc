"""
Accuracy slice — prediction-vs-actual tracking over time.

Feeds the Monitoring UI with a simple daily accuracy trend + a headline summary
(latest accuracy, 7-day average, week-over-week change, typical units off, drift flag).

Fabric-first: reads the notebook-written cfc_pred_vs_actual / cfc_daily_accuracy tables
when USE_FABRIC is on; falls back to the local backtest parquet via DuckDB otherwise.
Both paths are Decimal-tolerant. Neutral labels only (no method/metric names in the shape).

Endpoints:
  GET /accuracy/daily?days=30 -> {rows:[{dt, accuracy, units_off, n_rows, wmape}], source}
  GET /accuracy/summary       -> {latest_accuracy, accuracy_7d_avg, accuracy_change_7d,
                                  units_off, drift, source}
"""
from __future__ import annotations
import pathlib
from fastapi import APIRouter, Query

import duckdb

router = APIRouter(prefix="/accuracy", tags=["accuracy"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BP = ROOT / "data" / "predictions" / "backtest_preds.parquet"


def _f(v, nd=None):
    """Decimal/None-tolerant float. nd=None -> raw float."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if nd is not None else f


def _daily_fabric(days: int) -> list[dict] | None:
    """Per-day accuracy from Fabric. Prefers the pre-aggregated cfc_daily_accuracy table,
    else aggregates cfc_pred_vs_actual on the fly. None if off/unavailable/empty."""
    from deps import fabric
    if not fabric.enabled():
        return None
    # 1) pre-aggregated daily table
    try:
        DA = fabric.table("cfc_daily_accuracy")
        rows = fabric.q(f"SELECT TOP (?) dt, accuracy, wmape, units_off, n_rows "
                        f"FROM {DA} ORDER BY dt DESC", (days,))
        if rows:
            out = [{
                "dt": str(r.get("dt")),
                "accuracy": _f(r.get("accuracy"), 4),
                "units_off": _f(r.get("units_off"), 1),
                "n_rows": int(r["n_rows"]) if r.get("n_rows") is not None else None,
                "wmape": _f(r.get("wmape"), 4),
            } for r in rows]
            return out[::-1]  # oldest -> newest
    except Exception:
        pass
    # 2) aggregate the raw pred-vs-actual table
    try:
        PA = fabric.table("cfc_pred_vs_actual")
        rows = fabric.q(
            f"SELECT TOP (?) dt, "
            f"1 - SUM(ABS(y_actual - y_pred)) / NULLIF(SUM(y_actual), 0) accuracy, "
            f"SUM(ABS(y_actual - y_pred)) / NULLIF(SUM(y_actual), 0) wmape, "
            f"AVG(ABS(y_actual - y_pred)) units_off, COUNT(*) n_rows "
            f"FROM {PA} GROUP BY dt ORDER BY dt DESC", (days,))
        if rows:
            out = [{
                "dt": str(r.get("dt")),
                "accuracy": _f(r.get("accuracy"), 4),
                "units_off": _f(r.get("units_off"), 1),
                "n_rows": int(r["n_rows"]) if r.get("n_rows") is not None else None,
                "wmape": _f(r.get("wmape"), 4),
            } for r in rows]
            return out[::-1]
    except Exception:
        pass
    return None


def _daily_local(days: int) -> list[dict]:
    """Per-day accuracy from the local backtest parquet via DuckDB."""
    if not BP.exists():
        return []
    try:
        c = duckdb.connect(":memory:")
        bp = BP.as_posix()
        rows = c.execute(f"""
            SELECT CAST(date AS DATE) dt,
                   1 - SUM(ABS(y - p50)) / NULLIF(SUM(y), 0) AS accuracy,
                   SUM(ABS(y - p50)) / NULLIF(SUM(y), 0)     AS wmape,
                   AVG(ABS(y - p50))                         AS units_off,
                   COUNT(*)                                  AS n_rows
            FROM read_parquet('{bp}')
            GROUP BY 1 ORDER BY 1 DESC LIMIT {int(days)}
        """).fetchall()
        c.close()
        out = [{
            "dt": str(r[0]),
            "accuracy": _f(r[1], 4),
            "wmape": _f(r[2], 4),
            "units_off": _f(r[3], 1),
            "n_rows": int(r[4]) if r[4] is not None else None,
        } for r in rows]
        return out[::-1]  # oldest -> newest
    except Exception:
        return []


@router.get("/daily")
def daily(days: int = Query(30, ge=1, le=365)):
    fab = _daily_fabric(days)
    if fab is not None:
        return {"rows": fab, "source": "fabric"}
    return {"rows": _daily_local(days), "source": "local"}


def _drift_flag() -> bool | None:
    """Latest drift verdict from Fabric cfc_drift (accuracy drift), or None."""
    from deps import fabric
    if not fabric.enabled():
        return None
    try:
        rows = fabric.q(f"SELECT TOP 1 accuracy_drift FROM {fabric.table('cfc_drift')} ORDER BY ts DESC")
        if rows:
            return bool(rows[0].get("accuracy_drift"))
    except Exception:
        return None
    return None


@router.get("/summary")
def summary():
    fab = _daily_fabric(60)
    if fab is not None and fab:
        rows, source = fab, "fabric"
    else:
        rows, source = _daily_local(60), "local"

    accs = [r["accuracy"] for r in rows if r.get("accuracy") is not None]
    latest = accs[-1] if accs else None
    last7 = accs[-7:]
    prev7 = accs[-14:-7]
    avg7 = round(sum(last7) / len(last7), 4) if last7 else None
    avg_prev7 = (sum(prev7) / len(prev7)) if prev7 else None
    change7 = round(avg7 - avg_prev7, 4) if (avg7 is not None and avg_prev7 is not None) else None
    units = rows[-1]["units_off"] if rows and rows[-1].get("units_off") is not None else None

    drift = _drift_flag()
    if drift is None:
        # local heuristic: accuracy slipped notably vs the prior week
        drift = bool(change7 is not None and change7 < -0.05)

    return {
        "latest_accuracy": latest,
        "accuracy_7d_avg": avg7,
        "accuracy_change_7d": change7,
        "units_off": units,
        "drift": drift,
        "source": source,
    }
