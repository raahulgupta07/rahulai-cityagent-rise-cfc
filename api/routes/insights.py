"""
Gap-payoff insights slice — Wave-3 P8.

Prefix: /insights
Auto-mounted by routes/__init__.py. Never edit main.py.

Endpoints:
  GET /insights/stockout-correction  — zero-sold vs sold-out split (needs inventory_daily)
  GET /insights/promo-uplift         — demand lift on promo days vs baseline (needs promo_calendar)
  GET /insights/economics-impact     — uniform vs differentiated critical-ratio analysis (uses product_econ.csv)
"""
from __future__ import annotations
import pathlib, logging
import duckdb
import pandas as pd

from fastapi import APIRouter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["insights"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW  = ROOT / "data" / "raw"
EXT  = ROOT / "data" / "external"
ECON = ROOT / "data" / "product_econ.csv"

# ── helpers ──────────────────────────────────────────────────────────────────

def _find_file(*candidates: pathlib.Path) -> pathlib.Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


def _duck_read(path: pathlib.Path) -> pd.DataFrame:
    c = duckdb.connect(":memory:")
    return c.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stockout-correction")
def stockout_correction():
    """
    Splits zero-sold days into:
      (a) true demand zeros (product/branch genuinely had no customers)
      (b) stockout zeros (inventory hit zero during the day)

    Requires inventory_daily.parquet (or inventory_daily.csv) uploaded via /data/upload/inventory_daily.
    Without it, returns {available: false} with an explanation.
    """
    inv_path = _find_file(
        RAW / "inventory_daily.parquet",
        ROOT / "data" / "inventory_daily.parquet",
        ROOT / "data" / "inventory_daily.csv",
    )

    if inv_path is None:
        return {
            "available": False,
            "needs": "inventory_daily",
            "upload_path": "/data/upload/inventory_daily",
            "explanation": (
                "This view needs a daily inventory file with at minimum: "
                "BranchId, ProductId, date, closing_stock (or wasted_units). "
                "When closing_stock = 0 on a day where net_units = 0, that is a probable stockout. "
                "Upload the file to unlock the zero-demand breakdown and see how many "
                "'zero sales' days were actually stockout events."
            ),
            "potential_value": (
                "In the current demand panel there are many zero-unit days. "
                "Knowing which are real zeros vs stockouts improves forecast accuracy, "
                "especially for Class-A products where under-ordering erodes revenue."
            ),
        }

    # ── have inventory data — compute the split ──────────────────────────────
    try:
        dp = RAW / "demand_panel.parquet"
        if not dp.exists():
            return {"available": False, "needs": "demand_panel", "explanation": "demand_panel.parquet not found."}

        c = duckdb.connect(":memory:")

        # Load demand zeros
        demand_zeros_sql = f"""
            SELECT
                BranchId, ProductId, DayKey,
                SUM(net_units) AS net_units
            FROM read_parquet('{dp.as_posix()}')
            GROUP BY BranchId, ProductId, DayKey
            HAVING SUM(net_units) = 0
        """

        # Load inventory
        if inv_path.suffix == ".parquet":
            inv_sql = f"SELECT * FROM read_parquet('{inv_path.as_posix()}')"
        else:
            inv_df = pd.read_csv(inv_path)
            c.register("inv_tbl", inv_df)
            inv_sql = "SELECT * FROM inv_tbl"

        # Try to detect stockout column (closing_stock, close_stock, stock_close, end_stock, eod_stock)
        inv_cols_raw = c.execute(f"DESCRIBE ({inv_sql})").fetchall()
        inv_cols = [r[0].lower() for r in inv_cols_raw]
        stock_col = next(
            (r[0] for r in inv_cols_raw
             if r[0].lower() in ("closing_stock", "close_stock", "stock_close",
                                 "end_stock", "eod_stock", "qty_close", "closing_qty")),
            None,
        )

        if stock_col is None:
            return {
                "available": False,
                "needs": "inventory_daily",
                "explanation": (
                    "Inventory file found but no recognised closing-stock column. "
                    f"Detected columns: {', '.join(inv_cols[:10])}. "
                    "Expected one of: closing_stock, close_stock, stock_close, end_stock, eod_stock."
                ),
            }

        # Detect date / branch / product columns
        date_col    = next((r[0] for r in inv_cols_raw if r[0].lower() in ("date","day","daykey","day_key")), None)
        branch_col  = next((r[0] for r in inv_cols_raw if r[0].lower() in ("branchid","branch_id","branch")), None)
        product_col = next((r[0] for r in inv_cols_raw if r[0].lower() in ("productid","product_id","product")), None)

        if not all([date_col, branch_col, product_col]):
            missing = [n for n, v in [("date", date_col), ("BranchId", branch_col), ("ProductId", product_col)] if v is None]
            return {
                "available": False,
                "needs": "inventory_daily",
                "explanation": f"Inventory file missing columns: {', '.join(missing)}.",
            }

        # Compute split
        result = c.execute(f"""
            WITH demand_zeros AS ({demand_zeros_sql}),
            inv AS ({inv_sql})
            SELECT
                COUNT(*) AS total_zero_days,
                SUM(CASE WHEN inv."{stock_col}" = 0 THEN 1 ELSE 0 END) AS probable_stockout_days,
                SUM(CASE WHEN inv."{stock_col}" > 0 THEN 1 ELSE 0 END) AS true_zero_days,
                SUM(CASE WHEN inv."{stock_col}" IS NULL THEN 1 ELSE 0 END) AS no_inventory_match
            FROM demand_zeros dz
            LEFT JOIN inv
                ON inv."{branch_col}"  = dz.BranchId
               AND inv."{product_col}" = dz.ProductId
               AND CAST(inv."{date_col}" AS VARCHAR) = dz.DayKey
        """).fetchone()

        total, stockouts, true_zeros, no_match = result
        stockout_pct = round(stockouts / total * 100, 1) if total else 0

        return {
            "available": True,
            "summary": {
                "total_zero_demand_days": int(total),
                "probable_stockout_days": int(stockouts),
                "true_zero_demand_days": int(true_zeros),
                "no_inventory_match_days": int(no_match),
                "stockout_pct_of_zeros": stockout_pct,
            },
            "interpretation": (
                f"{stockout_pct}% of zero-demand days appear to be stockouts "
                f"({stockouts:,} of {total:,} zero days had closing stock = 0). "
                "These are missed revenue days, not true demand zeros. "
                "Removing them from the training target improves forecast accuracy "
                "and the system's ability to recommend the right order quantity."
            ),
        }
    except Exception as exc:
        log.exception("stockout-correction error")
        return {"available": False, "needs": "inventory_daily", "explanation": f"Computation error: {exc}"}


@router.get("/promo-uplift")
def promo_uplift():
    """
    Computes demand lift on promotional days vs baseline.

    Requires promo_calendar.parquet or promo_calendar.csv uploaded via /data/upload/promo_calendar.
    Without it, returns {available: false}.
    """
    promo_path = _find_file(
        RAW / "promo_calendar.parquet",
        ROOT / "data" / "promo_calendar.parquet",
        ROOT / "data" / "promo_calendar.csv",
        EXT / "promo_calendar.csv",
    )

    if promo_path is None:
        return {
            "available": False,
            "needs": "promo_calendar",
            "upload_path": "/data/upload/promo_calendar",
            "explanation": (
                "This view needs a promotions calendar with at minimum: "
                "date (or start_date/end_date), and optionally BranchId or ProductId for scoped promos. "
                "The system will compute average demand lift on promo days vs the 7-day baseline "
                "on non-promo days for the same (branch, product). "
                "Upload the file to unlock promo-uplift quantification."
            ),
            "potential_value": (
                "Knowing promo uplift lets the model differentiate planned spike days from noise, "
                "reducing over-ordering on non-promo days and under-ordering on promo days. "
                "Industry uplift for bakery promo events is typically 20–60%."
            ),
        }

    # ── have promo data — compute uplift ────────────────────────────────────
    try:
        dp = RAW / "demand_panel.parquet"
        if not dp.exists():
            return {"available": False, "needs": "demand_panel", "explanation": "demand_panel.parquet not found."}

        c = duckdb.connect(":memory:")

        if promo_path.suffix == ".parquet":
            promo_sql = f"SELECT * FROM read_parquet('{promo_path.as_posix()}')"
        else:
            promo_df = pd.read_csv(promo_path, parse_dates=True)
            c.register("promo_tbl", promo_df)
            promo_sql = "SELECT * FROM promo_tbl"

        # Detect date column
        promo_cols_raw = c.execute(f"DESCRIBE ({promo_sql})").fetchall()
        promo_cols = [r[0].lower() for r in promo_cols_raw]
        date_col = next(
            (r[0] for r in promo_cols_raw if r[0].lower() in ("date", "promo_date", "event_date", "start_date")),
            None,
        )

        if date_col is None:
            return {
                "available": False,
                "needs": "promo_calendar",
                "explanation": (
                    f"Promo file found but no recognised date column. "
                    f"Detected columns: {', '.join(promo_cols[:10])}. "
                    "Expected one of: date, promo_date, event_date, start_date."
                ),
            }

        # Aggregate demand per day
        demand_daily = c.execute(f"""
            SELECT
                DayKey,
                SUM(net_units) AS daily_units,
                COUNT(DISTINCT BranchId || '-' || CAST(ProductId AS VARCHAR)) AS series_count
            FROM read_parquet('{dp.as_posix()}')
            GROUP BY DayKey
        """).df()
        c.register("demand_daily", demand_daily)

        promo_days_count = c.execute(f"SELECT COUNT(DISTINCT CAST(\"{date_col}\" AS VARCHAR)) FROM ({promo_sql})").fetchone()[0]

        uplift = c.execute(f"""
            WITH promo_dates AS (
                SELECT DISTINCT REPLACE(CAST(\"{date_col}\" AS VARCHAR), '-', '') AS promo_day
                FROM ({promo_sql})
            )
            SELECT
                AVG(CASE WHEN pd.promo_day IS NOT NULL THEN d.daily_units END) AS promo_avg,
                AVG(CASE WHEN pd.promo_day IS NULL     THEN d.daily_units END) AS baseline_avg,
                COUNT(CASE WHEN pd.promo_day IS NOT NULL THEN 1 END) AS matched_promo_days
            FROM demand_daily d
            LEFT JOIN promo_dates pd ON pd.promo_day = d.DayKey
        """).fetchone()

        promo_avg, baseline_avg, matched = uplift
        lift_pct = round((promo_avg - baseline_avg) / baseline_avg * 100, 1) if baseline_avg else None

        return {
            "available": True,
            "summary": {
                "promo_days_in_calendar": int(promo_days_count),
                "matched_demand_days": int(matched) if matched else 0,
                "promo_avg_daily_units": round(float(promo_avg), 1) if promo_avg else None,
                "baseline_avg_daily_units": round(float(baseline_avg), 1) if baseline_avg else None,
                "lift_pct": lift_pct,
            },
            "interpretation": (
                f"Promo days show {lift_pct:+.1f}% demand vs non-promo baseline "
                f"({round(float(promo_avg),0):,.0f} vs {round(float(baseline_avg),0):,.0f} units/day). "
                "The model will use this to adjust forecasts on promo days."
            ) if lift_pct is not None else "Insufficient overlap between promo calendar and demand data.",
        }
    except Exception as exc:
        log.exception("promo-uplift error")
        return {"available": False, "needs": "promo_calendar", "explanation": f"Computation error: {exc}"}


@router.get("/economics-impact")
def economics_impact():
    """
    Compares ordering under current product_econ.csv (uniform vs differentiated critical ratio).

    This insight is always computable — product_econ.csv is auto-stubbed. The question is
    whether it has real per-product margins/shelf-lives or just the demo uniform values.
    """
    if not ECON.exists():
        return {
            "available": False,
            "needs": "product_economics",
            "upload_path": "/data/upload/product_economics",
            "explanation": (
                "product_econ.csv not found. "
                "This should have been auto-created — run `python3 src/order_qty.py build` to regenerate."
            ),
        }

    try:
        econ = pd.read_csv(ECON)
        n = len(econ)

        # Check uniformity
        gm_unique    = econ["gm"].nunique() if "gm" in econ.columns else 0
        shelf_unique = econ["shelf_life_days"].nunique() if "shelf_life_days" in econ.columns else 0
        is_uniform   = (gm_unique <= 1) and (shelf_unique <= 1)

        gm_values    = econ["gm"].describe().to_dict() if "gm" in econ.columns else {}
        shelf_values = econ["shelf_life_days"].describe().to_dict() if "shelf_life_days" in econ.columns else {}

        # Compute critical ratios: CR = Cu / (Cu + Co)
        # Cu = price * gm, Co = (price * (1 - gm) - salvage) * spoil_frac, spoil_frac = 1/shelf_life_days
        if all(c in econ.columns for c in ["ListPrice", "gm", "shelf_life_days", "salvage_frac"]):
            econ = econ.dropna(subset=["ListPrice", "gm", "shelf_life_days"])
            econ = econ[econ["ListPrice"] > 0]
            econ["cu"]          = econ["ListPrice"] * econ["gm"]
            econ["spoil_frac"]  = 1.0 / econ["shelf_life_days"].clip(lower=0.5)
            salvage_col         = econ.get("salvage_frac", pd.Series(0.0, index=econ.index))
            econ["co"]          = (econ["ListPrice"] * (1 - econ["gm"]) - salvage_col * econ["ListPrice"]) * econ["spoil_frac"]
            econ["co"]          = econ["co"].clip(lower=0)
            econ["cr"]          = econ["cu"] / (econ["cu"] + econ["co"].replace(0, 0.001))
            cr_stats            = econ["cr"].describe().to_dict()
            cr_spread           = round(float(econ["cr"].max() - econ["cr"].min()), 4)
        else:
            cr_stats  = {}
            cr_spread = 0.0

        # Insight: if all CRs are the same, newsvendor collapses to a flat percentile
        # and there's no differentiation — editing econ unlocks per-product targeting
        if is_uniform:
            message = (
                f"All {n} products use the same economics (GM={econ['gm'].iloc[0]:.0%}, "
                f"shelf life={econ['shelf_life_days'].iloc[0]:.0f}d). "
                "This means the newsvendor model orders every product at the same demand percentile — "
                "no differentiation between high-margin fresh pastries and low-margin long-shelf items. "
                "Edit product_econ.csv with real per-product gross margin and shelf life to unlock "
                "differentiated ordering: fresh/high-margin items get higher order quantities "
                "while long-shelf/low-margin items are ordered more conservatively."
            )
            unlock_value = (
                "Per-product economics typically shifts 15–30% of order quantities, "
                "cutting waste on slow-moving items while protecting revenue on high-margin bestsellers."
            )
        else:
            cr_min = round(float(econ["cr"].min()), 3) if "cr" in econ.columns else None
            cr_max = round(float(econ["cr"].max()), 3) if "cr" in econ.columns else None
            message = (
                f"Real economics loaded for {n} products. "
                f"Critical ratios span {cr_min} → {cr_max} (spread {cr_spread:.3f}). "
                "The newsvendor model is now ordering each product at its own optimal "
                "demand percentile — fresh high-margin items get more buffer; "
                "long-shelf items are ordered closer to median demand."
            )
            unlock_value = None

        return {
            "available": True,
            "is_uniform": is_uniform,
            "product_count": n,
            "gm_stats": {k: round(float(v), 4) for k, v in gm_values.items() if isinstance(v, float)},
            "shelf_life_stats": {k: round(float(v), 2) for k, v in shelf_values.items() if isinstance(v, float)},
            "critical_ratio_stats": {k: round(float(v), 4) for k, v in cr_stats.items() if isinstance(v, float)},
            "critical_ratio_spread": cr_spread,
            "message": message,
            "unlock_value": unlock_value,
            "action": None if not is_uniform else "Upload real per-product economics via /data/upload/product_economics",
        }

    except Exception as exc:
        log.exception("economics-impact error")
        return {
            "available": False,
            "needs": "product_economics",
            "explanation": f"Could not parse product_econ.csv: {exc}",
        }
